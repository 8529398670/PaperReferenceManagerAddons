// The Lists screen: hand-ordered, tagged lists of papers.
//
// Every change is a batch of ops sent to POST /api/lists/<slug>/ops (the same
// ops an API key or an MCP agent sends; app/boards/ops.py has them all). The
// answer carries the list as it now is, which is drawn as it comes. There is
// no whole-list save, so there is nothing to merge and no draft to keep: what
// is on screen is what the server has.
//
// Every change is undoable, as one step however many rows it touched. Most
// carry the ops that put them back, worked out before they are sent; the big
// ones (order by, the shelf, an import) are undone by putting back the
// version the server kept from just before them (changeWhole).
//
// Live: /api/lists/stream says "list X is at rev N" whenever any list changes,
// from another tab, another person or an agent; the open list is fetched again
// when that is newer than what is showing.
//
// This file holds the state, the sending and the adding; board_view.js draws
// rows, list_tools.js the tag bar, selection, filter and moving around, and
// list_panels.js the list menu's dialogs.
const Lists = {
  me: null,
  lists: [],
  slug: null,
  paperContext: { slug: "" , name: "" , keys: [] },
  view: null,
  items: new Map(),
  positions: new Map(),
  storageKey: "lists-open",
  stream: null,
  // Changes this page has sent and not heard back about. While there are any,
  // a live "the list moved" is most likely the echo of one of them, and is
  // held until they are answered (heard).
  sending: 0,
  heard: 0,
  claimedColors: new Set(),
  // key -> { intext , full } in `citeStyle`, filled in the background.
  cites: {},
  citeStyle: "",
  citing: false,
  // key -> how a staged reference matched ("doi", "title", "fuzzy").
  matched: {},
  // Ticked rows on the shelf.
  checked: new Set(),
  // The add box's hits.
  hits: [],
  hitsKind: "search",
  picked: new Set(),
  active: -1,
  pickAnchor: -1,
  addTicket: 0,
  addTimer: null,

  async init( me ) {
    this.me = me;
    Dom.show( Dom.get( "lists-panel" ) , true );
    // Tag colours can follow the theme (TagColors): repaint when they moved.
    let palette = TagColors.palette.join();
    Theme.onChange.push( () => {
      const now = TagColors.palette.join();
      if ( now === palette ) return;
      palette = now;
      this.draw();
    } );
    this.compactOnScroll();
    window.addEventListener( "hashchange" , () => {
      // After Nav has shown the screen, so the board has its size.
      if ( this.drawLater && Nav.current() === "lists" ) setTimeout( () => this.draw() , 0 );
    } );
    Dom.get( "list-picker" ).addEventListener( "change" , ( event ) => this.open( event.target.value ) );
    Dom.get( "list-new" ).addEventListener( "click" , () => this.showNewForm( true ) );
    Dom.get( "list-new-cancel" ).addEventListener( "click" , () => this.showNewForm( false ) );
    Dom.onSubmit( Dom.get( "list-new-form" ) , this.onCreate.bind( this ) );
    this.initAdd();
    ListTools.init( this );
    ListPanels.init( this );
    TagMenu.init( this );
    BoardColumns.init( this );
    ListManage.init( this );
    ListSheet.init( this );
    await this.loadLists();
    this.listen();
  },

  // ---- which list -------------------------------------------------------

  local( key , value ) {
    try {
      if ( value === undefined ) return window.localStorage.getItem( key );
      if ( value === null ) window.localStorage.removeItem( key );
      else window.localStorage.setItem( key , value );
    } catch ( error ) { /* only a convenience */ }
    return null;
  },

  async loadLists( choose ) {
    const answer = await Api.request( "/api/lists?limit=1000" );
    this.lists = answer.lists;
    const picker = Dom.get( "list-picker" );
    picker.replaceChildren( ...this.lists.map( ( list ) => Dom.el( "option" , { text: list.name , attrs: { value: list.slug } } ) ) );
    Dom.show( picker , this.lists.length > 0 );
    Dom.show( Dom.get( "list-menu-holder" ) , this.lists.length > 0 );
    Dom.show( Dom.get( "lists-none" ) , this.lists.length === 0 );
    Dom.show( Dom.get( "list-body" ) , this.lists.length > 0 );
    if ( this.lists.length === 0 ) {
      this.view = null;
      Dom.text( Dom.get( "list-count" ) , "" );
      return;
    }
    // A link (#lists/<slug>) wins on the first load; a slug renamed away from
    // still opens, as the list it became.
    const linked = this.slug ? null : ListManage.hashSlug();
    if ( linked && !choose && !this.lists.some( ( list ) => list.slug === linked ) ) {
      try {
        await this.open( linked );
        return;
      } catch ( error ) {
        ListManage.cannotOpen( error );
      }
    }
    const wanted = [ choose , linked , this.slug , this.local( this.storageKey ) , "main" ].find( ( slug ) => slug && this.lists.some( ( list ) => list.slug === slug ) );
    await this.open( wanted || this.lists[ 0 ].slug );
  },

  async open( asked ) {
    const answer = await Api.request( "/api/lists/" + encodeURIComponent( asked ) );
    const slug = answer.list.slug;
    if ( slug !== this.slug ) {
      // Another list: what was picked, ticked and painted belonged to the last.
      ListTools.forget();
      this.checked.clear();
      this.matched = {};
      this.cites = {};
      BoardView.reset( Dom.get( "list-rows" ) );
      BoardView.reset( Dom.get( "list-shelf-rows" ) );
    }
    this.slug = slug;
    this.local( this.storageKey , slug );
    Dom.get( "list-picker" ).value = slug;
    ListManage.showInHash( slug );
    this.take( answer.list );
  },

  // A list as the server sent it: index it, draw it.
  take( view ) {
    this.view = view;
    this.items = new Map();
    this.positions = new Map();
    // On a tier board a row's number is its rank in its tier.
    this.sectionCounts = {};
    ( view.doc.items || [] ).forEach( ( item , index ) => {
      this.items.set( item.key , item );
      if ( item.section ) {
        this.sectionCounts[ item.section ] = ( this.sectionCounts[ item.section ] || 0 ) + 1;
        this.positions.set( item.key , this.sectionCounts[ item.section ] );
      } else {
        this.positions.set( item.key , index + 1 );
      }
    } );
    this.shelfItems = new Map( ( view.doc.staging || [] ).map( ( item ) => [ item.key , item ] ) );
    const entry = this.lists.find( ( list ) => list.slug === view.slug );
    if ( entry ) Object.assign( entry , { name: view.name , locked: view.locked , rev: view.rev } );
    this.draw();
    this.fetchCites();
  },

  showNewForm( visible ) {
    Dom.show( Dom.get( "list-new-form" ) , visible );
    if ( visible ) Dom.get( "list-new-name" ).focus();
  },

  async onCreate( event ) {
    event.preventDefault();
    const name = Dom.get( "list-new-name" ).value.trim();
    if ( !name ) return;
    const made = await ListManage.create( { name: name } , "undo.list_create" );
    if ( made ) {
      Dom.get( "list-new-name" ).value = "";
      this.showNewForm( false );
    }
  },

  // ---- drawing -------------------------------------------------------------

  // The columns drawn: every one not unticked in the Columns menu.
  // Scrolled down the board, the cards above it (the list picker, adding a
  // paper, the shelf) fold away and the board takes the screen, toolbar and
  // column labels kept, like the other table screens. Back at the top they
  // return. From md up only, where the board scrolls by itself (on a phone
  // the whole page scrolls, so they scroll away anyway). Not while something
  // up there is in use, and not on a list too short to scroll past them, or
  // folding would take away the scroll that folded it.
  compactOnScroll() {
    const panel = Dom.get( "lists-panel" );
    const board = Dom.get( "list-scroll" );
    const wide = window.matchMedia( "(min-width: 768px)" );
    const tops = () => [ panel.querySelector( ":scope > .card" ) , Dom.get( "list-view-only" ) , Dom.get( "list-editing" ) , Dom.get( "list-shelf" ) ];
    let frame = 0;
    const check = () => {
      frame = 0;
      const compact = panel.classList.contains( "is-compact" );
      let want = compact;
      if ( !wide.matches ) want = false;
      else if ( board.scrollTop <= 4 ) want = false;
      else if ( !compact && board.scrollTop > 48 ) {
        const busy = tops().some( ( element ) => element && element.contains( document.activeElement ) )
          || !Dom.get( "list-add-panel" ).hidden || !Dom.get( "list-new-form" ).hidden;
        const room = tops().reduce( ( sum , element ) => sum + ( element && !element.hidden ? element.offsetHeight : 0 ) , 0 );
        want = !busy && board.scrollHeight - board.clientHeight > room + 200;
      }
      if ( want !== compact ) panel.classList.toggle( "is-compact" , want );
    };
    board.addEventListener( "scroll" , () => {
      if ( !frame ) frame = window.requestAnimationFrame( check );
    } , { passive: true } );
    wide.addEventListener( "change" , check );
    // Another list starts at its top, with everything showing.
    Dom.get( "list-picker" ).addEventListener( "change" , () => panel.classList.remove( "is-compact" ) );
  },

  columns() {
    const doc = this.view.doc;
    const folded = new Set( ( doc.options && doc.options.fold_cols ) || [] );
    return ( doc.columns || [] ).filter( ( column ) => !folded.has( column.id ) );
  },

  draw() {
    const view = this.view;
    if ( !view ) return;
    // Not while another screen shows: the board is drawn when it is next
    // opened (the hashchange in init), so the Library is not kept waiting.
    if ( Nav.current() !== "lists" ) {
      this.drawLater = true;
      return;
    }
    this.drawLater = false;
    const started = performance.now();
    const doc = view.doc;
    const count = ( doc.items || [] ).length;
    Dom.text( Dom.get( "list-count" ) , I18n.get( "lists.count" ).replace( "{count}" , count.toLocaleString() ) );
    Dom.show( Dom.get( "list-view-only" ) , view.locked );
    Dom.get( "lists-panel" ).classList.toggle( "is-locked" , Boolean( view.locked ) );
    const columns = this.columns();
    const colSig = columns.map( ( column ) => column.id + "=" + column.label ).join( "|" );
    if ( colSig !== this.lastColSig ) {
      this.lastColSig = colSig;
      BoardColumns.head( Dom.get( "list-head" ) , columns );
    }
    BoardColumns.layout( columns );

    const visible = ( doc.items || [] ).filter( ( item ) => ListTools.matches( item , view.papers[ item.key ] ) ).map( ( item ) => item.key );
    const handlers = this.handlers();
    const anchor = ListTools.anchor();
    // One object, updated in place, so a row drawn before still steps through
    // the list as it is now (Paper screen's Prev / Next).
    this.paperContext.slug = this.slug;
    this.paperContext.name = view.name || this.slug;
    // Only papers in the library have a Paper screen to step to.
    this.paperContext.keys = visible.filter( ( key ) => ( view.papers[ key ] || {} ).in_library !== false );
    BoardView.render( Dom.get( "list-rows" ) , {
      paperContext: this.paperContext,
      doc: doc , papers: view.papers || {} , handlers: handlers , locked: view.locked , columns: columns ,
      items: this.items , visible: visible , positions: this.positions , cites: this.cites , anchor: anchor ,
      sections: doc.sections || [] , sectionCounts: this.sectionCounts , target: ( doc.options && doc.options.section_target ) || "" ,
      lazy: true , scroller: Dom.get( "list-scroll" ) ,
    } );
    ListTools.paintSelection();
    this.drawShelf( columns , handlers );

    const filtered = Dom.get( "list-filtered" );
    const describe = ListTools.describe();
    Dom.text( filtered , I18n.get( "lists.filtered" ).replace( "{shown}" , visible.length.toLocaleString() ).replace( "{count}" , count.toLocaleString() ) + ( describe ? " · " + describe : "" ) );
    Dom.show( filtered , ListTools.filtering() );
    Dom.show( Dom.get( "list-empty" ) , count === 0 );
    const names = ListTools.tagNames();
    const options = Dom.get( "list-tag-options" );
    if ( options._names !== names.join( "\n" ) ) {
      options._names = names.join( "\n" );
      options.replaceChildren( ...names.map( ( name ) => Dom.el( "option" , { attrs: { value: name } } ) ) );
    }
    ListTools.drawBar();
    ListPanels.drawMenu();
    this.lastDrawMs = performance.now() - started;
  },

  drawShelf( columns , handlers ) {
    const doc = this.view.doc;
    const staged = doc.staging || [];
    const shelf = Dom.get( "list-shelf" );
    Dom.show( shelf , staged.length > 0 );
    for ( const key of Array.from( this.checked ) ) {
      if ( !this.shelfItems.has( key ) ) this.checked.delete( key );
    }
    BoardView.render( Dom.get( "list-shelf-rows" ) , {
      doc: doc , papers: this.view.papers || {} , handlers: handlers , locked: this.view.locked , columns: columns ,
      items: this.shelfItems , visible: staged.map( ( item ) => item.key ) , positions: new Map() , cites: {} ,
      shelf: true , matched: this.matched , checked: this.checked ,
    } );
    if ( staged.length === 0 ) return;
    Dom.text( Dom.get( "list-shelf-title" ) , I18n.get( "lists.shelf_title_count" ).replace( "{count}" , staged.length ) );
    const all = Dom.get( "list-shelf-all" );
    all.checked = this.checked.size === staged.length;
    all.indeterminate = this.checked.size > 0 && this.checked.size < staged.length;
    const n = this.checked.size || staged.length;
    Dom.text( Dom.get( "list-shelf-add" ) , I18n.get( this.checked.size ? "lists.shelf_add_checked" : "lists.shelf_add_all" ).replace( "{count}" , n ) );
    Dom.get( "list-shelf-drop" ).disabled = this.checked.size === 0;
  },

  handlers() {
    return {
      move: ( key , position ) => this.move( key , position ),
      moveNear: ( key , anchor , side ) => this.moveNear( key , anchor , side ),
      remove: ( key ) => this.remove( key ),
      addTag: ( key , name ) => this.addTag( [ key ] , name ),
      removeTag: ( key , name ) => this.removeTag( [ key ] , name ),
      setCell: ( key , column , value , previous ) => this.setCell( key , column , value , previous ),
      anchor: ( key ) => ListTools.toggleAnchor( key ),
      copy: ( text ) => this.copy( text ),
      setSection: ( key , section ) => this.toSection( [ key ] , section ),
      dropOnSection: ( key , section ) => this.toSection( this.dragged( key ) , section , 1 ),
      target: ( section ) => this.target( section ),
      rename: ( key , title , previous ) => this.change( "undo.list_title" , [ { op: "update" , row: key , title: title } ] , [ { op: "update" , row: key , title: previous } ] ),
      check: ( key , on ) => {
        if ( on ) this.checked.add( key );
        else this.checked.delete( key );
        this.drawShelf( this.columns() , this.handlers() );
      },
    };
  },

  state( key , text ) {
    Dom.text( Dom.get( "list-state" ) , text || ( key ? I18n.get( key ) : "" ) );
  },

  async copy( text ) {
    const holder = Dom.el( "span" , { text: text , class: "visually-hidden" } );
    document.body.appendChild( holder );
    try {
      await Dom.copy( holder );
    } finally {
      holder.remove();
    }
  },

  // ---- citations, in the background -------------------------------------------

  async fetchCites() {
    if ( this.citing || !this.view ) return;
    const slug = this.slug;
    const style = ( this.view.doc.options && this.view.doc.options.cite_style ) || "";
    if ( style !== this.citeStyleWanted ) {
      this.citeStyleWanted = style;
      this.cites = {};
    }
    const missing = ( this.view.doc.items || [] ).map( ( item ) => item.key ).filter( ( key ) => !( key in this.cites ) );
    if ( missing.length === 0 ) return;
    this.citing = true;
    try {
      for ( let at = 0 ; at < missing.length ; at += 150 ) {
        const answer = await Api.post( "/api/cite" , { keys: missing.slice( at , at + 150 ) , list: slug } );
        if ( slug !== this.slug ) return;
        Object.assign( this.cites , answer.cites );
        this.citeStyle = answer.style;
        this.draw();
      }
    } catch ( error ) {
      // Citations are a nicety: the rows stand without them.
    } finally {
      this.citing = false;
    }
  },

  // ---- sending ---------------------------------------------------------------

  // Sends a batch to a list, draws the answer. The slug is fixed at the time
  // of the action, so an undo reaches the list it happened on even after
  // another one was opened.
  async send( slug , ops ) {
    this.state( "lists.saving" );
    this.sending += 1;
    try {
      const answer = await Api.post( "/api/lists/" + encodeURIComponent( slug ) + "/ops" , { ops: ops } );
      if ( slug === this.slug && answer.list ) this.take( answer.list );
      this.state( "lists.saved" );
      ListManage.report( answer.mirrored );
      return answer;
    } catch ( error ) {
      this.state( "" );
      throw error;
    } finally {
      this.sending -= 1;
      // Something newer than what came back arrived meanwhile: someone else.
      if ( this.sending === 0 && slug === this.slug && this.view && this.heard > this.view.rev ) {
        this.open( slug ).catch( () => {} );
      }
    }
  },

  // Puts back the version the server kept at `rev`, as a new version.
  async restoreTo( slug , rev ) {
    this.sending += 1;
    try {
      const answer = await Api.post( "/api/lists/" + encodeURIComponent( slug ) + "/restore" , { rev: rev } );
      if ( slug === this.slug && answer.list ) this.take( answer.list );
      return answer;
    } finally {
      this.sending -= 1;
    }
  },

  // One undoable change: ops now, back to put it back.
  async change( label , ops , back , options ) {
    const slug = this.slug;
    const settings = options || {};
    try {
      await Undo.run( {
        label: I18n.get( label ),
        toast: Boolean( settings.toast ),
        do: () => this.send( slug , ops ),
        undo: () => this.send( slug , back ),
      } );
      if ( settings.flash ) BoardView.flash( Dom.get( "list-rows" ) , settings.flash );
      return true;
    } catch ( error ) {
      this.failed( slug , error );
      return false;
    }
  },

  // One undoable change whose undo is the version kept from just before it:
  // for changes too wide to invert op by op (a new order, the shelf, imports).
  async changeWhole( label , ops , options ) {
    const slug = this.slug;
    const settings = options || {};
    let before = null;
    let answer = null;
    try {
      await Undo.run( {
        label: I18n.get( label ),
        toast: settings.toast !== false,
        do: async () => {
          const rev = this.view.rev;
          const sent = await this.send( slug , ops );
          if ( sent.changed ) before = rev;
          answer = sent;
          return sent;
        },
        undo: () => ( before === null ? Promise.resolve() : this.restoreTo( slug , before ) ),
      } );
      return answer;
    } catch ( error ) {
      this.failed( slug , error );
      return null;
    }
  },

  failed( slug , error ) {
    Dom.toast( error.message , "error" );
    // What is on screen may be ahead of the server now: ask again.
    if ( slug === this.slug ) this.open( slug ).catch( () => {} );
  },

  move( key , position ) {
    const at = this.positions.get( key );
    if ( !at ) return;
    const item = this.items.get( key );
    if ( item && item.section ) {
      // A rank in its own tier.
      this.toSection( [ key ] , item.section , position );
      return;
    }
    this.change( "undo.list_move" , [ { op: "move" , row: key , to: position } ] , [ { op: "move" , row: key , to: at } ] , { flash: key } );
  },

  // ---- tiers ---------------------------------------------------------------------

  // What a drag carries: the row, or the whole selection when it is part of one.
  dragged( key ) {
    const selected = ListTools.selectedKeys();
    return selected.length > 1 && selected.includes( key ) ? selected : [ key ];
  },

  // Rows into a tier, at a rank among its other rows (its end by default).
  // One row is undone by putting it back where it was; several by the version.
  toSection( keys , section , rank ) {
    const op = { op: "section_set" , rows: keys , section: section };
    if ( rank ) op.rank = rank;
    if ( keys.length > 1 ) return this.changeWhole( "undo.list_tier" , [ op ] , { toast: false } );
    const item = this.items.get( keys[ 0 ] );
    if ( !item ) return Promise.resolve( false );
    const back = { op: "section_set" , rows: keys , section: item.section , rank: this.positions.get( keys[ 0 ] ) };
    return this.change( "undo.list_tier" , [ op ] , [ back ] , { flash: keys[ 0 ] } );
  },

  target( section ) {
    const old = ( this.view.doc.options && this.view.doc.options.section_target ) || "unranked";
    if ( old === section ) return;
    this.change( "undo.list_target" , [ { op: "section_target" , section: section } ] , [ { op: "section_target" , section: old } ] );
  },

  // Dropped next to another row. A selected row brings the whole selection.
  moveNear( key , anchor , side ) {
    const target = this.items.get( anchor );
    if ( target && target.section ) {
      // On a tier board: into the anchor's tier, next to it.
      const moving = this.dragged( key );
      const others = ( this.view.doc.items || [] ).filter( ( item ) => item.section === target.section && !moving.includes( item.key ) ).map( ( item ) => item.key );
      const at = others.indexOf( anchor );
      if ( at < 0 ) return;
      this.toSection( moving , target.section , at + 1 + ( side === "after" ? 1 : 0 ) );
      return;
    }
    const selected = ListTools.selectedKeys();
    if ( selected.length > 1 && selected.includes( key ) && !selected.includes( anchor ) ) {
      const to = {};
      to[ side ] = anchor;
      this.changeWhole( "undo.list_move" , [ { op: "reorder" , rows: selected , at: to } ] , { toast: false } );
      return;
    }
    const at = this.positions.get( key );
    if ( !at ) return;
    const to = {};
    to[ side ] = anchor;
    this.change( "undo.list_move" , [ { op: "move" , row: key , to: to } ] , [ { op: "move" , row: key , to: at } ] , { flash: key } );
  },

  remove( key ) {
    const item = this.items.get( key );
    if ( !item ) return;
    // Everything the row was, so putting it back loses nothing: its tags, its
    // cells, where it stood.
    const paper = { key: item.key , title: item.title || "" , doi: item.doi || "" , year: item.year || null , journal: item.journal || "" };
    if ( item.authors ) paper.authors = item.authors;
    const global = ( this.view.doc.items || [] ).findIndex( ( row ) => row.key === key ) + 1;
    const back = [ {
      op: "add" , paper: paper , at: global , tags: item.tags || [] ,
      cells: item.fields || {} , auto_tag: false , prefill: false ,
    } ];
    // Back into its own tier, at its own rank (an add lands in the target tier).
    if ( item.section ) back.push( { op: "section_set" , rows: [ key ] , section: item.section , rank: this.positions.get( key ) } );
    ListTools.unselect( key );
    this.change( "undo.list_remove" , [ { op: "remove" , rows: [ key ] } ] , back , { toast: true } );
  },

  row( key ) {
    return this.items.get( key ) || ( this.shelfItems && this.shelfItems.get( key ) ) || null;
  },

  vocabEntry( name ) {
    const vocab = ( this.view.doc.vocab && this.view.doc.vocab.tags ) || [];
    return vocab.find( ( tag ) => tag.name.toLowerCase() === String( name ).toLowerCase() ) || null;
  },

  // The ops that make `name` a tag of the list (with a colour of its own)
  // when it is not one yet, and their undo.
  createTag( name , ops , back ) {
    const known = this.vocabEntry( name );
    if ( known ) return known.name;
    const vocab = ( this.view.doc.vocab && this.view.doc.vocab.tags ) || [];
    const color = TagColors.next( vocab.concat( Array.from( this.claimedColors , ( claimed ) => ( { color: claimed } ) ) ) );
    this.claimedColors.add( color );
    setTimeout( () => this.claimedColors.delete( color ) , 5000 );
    ops.push( { op: "tag_create" , name: name , color: color } );
    back.push( { op: "tag_delete" , name: name } );
    return name;
  },

  autoMove() {
    return Boolean( this.view.doc.options && this.view.doc.options.auto_move );
  },

  // Tags rows (one row, or a selection) with name. Undo takes it off exactly
  // the rows that did not have it. With Auto-move on the rows may move too,
  // so that undo puts the version back instead.
  addTag( keys , name ) {
    const lacking = keys.filter( ( key ) => {
      const row = this.row( key );
      return row && !( row.tags || [] ).some( ( tag ) => tag.toLowerCase() === name.toLowerCase() );
    } );
    if ( lacking.length === 0 ) return Promise.resolve( true );
    const ops = [];
    const back = [];
    const real = this.createTag( name , ops , back );
    ops.push( { op: "tag" , rows: lacking , add: [ real ] } );
    back.unshift( { op: "tag" , rows: lacking , remove: [ real ] } );
    if ( this.autoMove() ) return this.changeWhole( "undo.list_tag" , ops , { toast: false } );
    return this.change( "undo.list_tag" , ops , back );
  },

  removeTag( keys , name ) {
    const having = keys.filter( ( key ) => {
      const row = this.row( key );
      return row && ( row.tags || [] ).some( ( tag ) => tag.toLowerCase() === name.toLowerCase() );
    } );
    if ( having.length === 0 ) return Promise.resolve( true );
    const ops = [ { op: "tag" , rows: having , remove: [ name ] } ];
    if ( this.autoMove() ) return this.changeWhole( "undo.list_tag" , ops , { toast: false } );
    return this.change( "undo.list_tag" , ops , [ { op: "tag" , rows: having , add: [ name ] } ] );
  },

  setCell( key , column , value , previous ) {
    this.change( "undo.list_note" ,
      [ { op: "set_cell" , row: key , col: column , value: value } ] ,
      [ { op: "set_cell" , row: key , col: column , value: previous } ] );
  },

  // ---- adding from the library: search, or what was saved recently ------------

  initAdd() {
    const add = Dom.get( "list-add" );
    add.addEventListener( "input" , () => {
      clearTimeout( this.addTimer );
      this.addTimer = setTimeout( () => this.search() , 150 );
    } );
    add.addEventListener( "keydown" , ( event ) => this.onAddKey( event ) );
    Dom.get( "list-add-results" ).addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Escape" ) {
        this.closeHits();
        add.focus();
      }
    } );
    Dom.onPress( Dom.get( "list-recent" ) , () => this.recent() );
    Dom.onPress( Dom.get( "list-add-picked" ) , () => this.addPicked() );
    Dom.get( "list-add-close" ).addEventListener( "click" , () => this.closeHits() );
    // Open while the pointer or the focus is in it: the hits have boxes of
    // their own (a tag, a position) to type in.
    document.addEventListener( "mousedown" , ( event ) => {
      if ( !Dom.get( "list-add-wrap" ).contains( event.target ) ) this.closeHits();
    } );
    Dom.get( "list-add-wrap" ).addEventListener( "focusout" , ( event ) => {
      if ( event.relatedTarget && !Dom.get( "list-add-wrap" ).contains( event.relatedTarget ) ) this.closeHits();
    } );
  },

  async search() {
    const text = Dom.get( "list-add" ).value.trim();
    const ticket = ++this.addTicket;
    if ( text.length < 2 ) {
      if ( this.hitsKind === "search" ) this.closeHits();
      return;
    }
    const params = new URLSearchParams( { q: text , mode: "title" , limit: "8" } );
    const answer = await Api.request( "/api/papers?" + params );
    if ( ticket !== this.addTicket ) return;
    this.showHits( "search" , answer.papers , "" );
  },

  async recent() {
    const days = Dom.get( "list-recent-days" ).value;
    const ticket = ++this.addTicket;
    const params = new URLSearchParams( { days: days , not_on: this.slug , limit: "200" } );
    const answer = await Api.request( "/api/papers/recent?" + params );
    if ( ticket !== this.addTicket ) return;
    this.recentRange = Dom.get( "list-recent-days" ).selectedOptions[ 0 ].textContent;
    this.recentTotal = answer.total;
    this.showHits( "recent" , answer.papers , this.recentHead() );
  },

  recentHead() {
    return I18n.get( "lists.recent_head" ).replace( "{range}" , () => this.recentRange ).replace( "{count}" , this.recentTotal );
  },

  showHits( kind , papers , head ) {
    this.hitsKind = kind;
    this.hits = papers.map( ( paper ) => Object.assign( {} , paper , { addTags: [] , at: "" } ) );
    this.picked = new Set();
    this.active = this.hits.length ? 0 : -1;
    this.pickAnchor = this.active;
    Dom.text( Dom.get( "list-add-head" ) , head );
    Dom.show( Dom.get( "list-add-head" ) , Boolean( head ) );
    this.drawHits();
  },

  drawHits() {
    const list = Dom.get( "list-add-results" );
    const items = this.hits.map( ( paper , index ) => this.hitRow( paper , index ) );
    if ( items.length === 0 ) {
      items.push( Dom.el( "li" , { class: "list-group-item text-body-secondary" , text: I18n.get( this.hitsKind === "recent" ? "lists.recent_nothing" : "lists.add_nothing" ) } ) );
    }
    list.replaceChildren( ...items );
    const button = Dom.get( "list-add-picked" );
    Dom.show( button , this.picked.size > 1 );
    Dom.text( button , I18n.get( "lists.add_picked" ).replace( "{count}" , this.picked.size ) );
    Dom.show( Dom.get( "list-add-panel" ) , true );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "true" );
    const active = list.querySelector( ".add-hit.active" );
    if ( active ) active.scrollIntoView( { block: "nearest" } );
  },

  hitRow( paper , index ) {
    const on = this.positions.get( paper.key );
    const picked = this.picked.has( index );
    const children = [
      Dom.el( "div" , { class: "paper-title" , text: paper.title } ),
      Dom.el( "div" , { class: "paper-meta" , text: PaperLinks.meta( paper ) } ),
    ];
    if ( on ) {
      children.push( Dom.el( "div" , { class: "small text-success" , text: I18n.get( "lists.add_on_list" ).replace( "{n}" , on ) } ) );
    } else {
      // A tag and a position for this one, so it arrives where and as it should.
      const tag = Dom.el( "input" , {
        class: "form-control form-control-sm tag-input",
        attrs: { type: "text" , list: "list-tag-options" , autocomplete: "off" , placeholder: I18n.get( "lists.tag_add_placeholder" ) , "aria-label": BoardView.label( "lists.tag_add_label" , paper.title ) },
      } );
      tag.value = paper.addTags.join( ", " );
      tag.addEventListener( "change" , () => {
        paper.addTags = tag.value.split( "," ).map( ( name ) => name.trim() ).filter( Boolean );
      } );
      const at = Dom.el( "input" , {
        class: "form-control form-control-sm board-row-num",
        attrs: { type: "text" , inputmode: "numeric" , placeholder: "#" , "aria-label": BoardView.label( "lists.add_at_label" , paper.title ) },
      } );
      at.value = paper.at;
      at.addEventListener( "change" , () => { paper.at = at.value.trim(); } );
      [ tag , at ].forEach( ( input ) => input.addEventListener( "keydown" , ( event ) => {
        if ( event.key === "Enter" ) {
          event.preventDefault();
          input.dispatchEvent( new Event( "change" ) );
          this.addHits( this.picked.has( index ) && this.picked.size > 1 ? Array.from( this.picked ) : [ index ] );
        }
      } ) );
      children.push( Dom.el( "div" , { class: "add-hit-extra" , children: [ tag , at ] } ) );
    }
    const element = Dom.el( "li" , {
      class: "list-group-item list-group-item-action add-hit" + ( index === this.active ? " active" : "" ) + ( picked ? " is-picked" : "" ),
      attrs: { role: "option" , "aria-selected": String( picked || index === this.active ) },
      children: children,
    } );
    element.addEventListener( "mousedown" , ( event ) => {
      if ( event.target.closest( "input" ) ) return;
      // Not the input's blur first.
      event.preventDefault();
      this.pickHit( index , event );
    } );
    element.addEventListener( "dblclick" , ( event ) => {
      if ( event.target.closest( "input" ) ) return;
      this.addHits( [ index ] );
    } );
    return element;
  },

  // Click picks one, Cmd/Ctrl-click adds or drops one, Shift-click a range.
  pickHit( index , event ) {
    if ( event.metaKey || event.ctrlKey ) {
      if ( this.picked.has( index ) ) this.picked.delete( index );
      else this.picked.add( index );
      this.pickAnchor = index;
    } else if ( event.shiftKey && this.pickAnchor >= 0 ) {
      const [ low , high ] = [ Math.min( this.pickAnchor , index ) , Math.max( this.pickAnchor , index ) ];
      this.picked = new Set();
      for ( let i = low ; i <= high ; i++ ) this.picked.add( i );
    } else {
      this.picked = new Set( [ index ] );
      this.pickAnchor = index;
    }
    this.active = index;
    this.drawHits();
  },

  closeHits() {
    Dom.show( Dom.get( "list-add-panel" ) , false );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "false" );
  },

  onAddKey( event ) {
    const open = !Dom.get( "list-add-panel" ).hidden;
    if ( event.key === "ArrowDown" || event.key === "ArrowUp" ) {
      if ( !open || !this.hits.length ) return;
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      this.active = ( this.active + step + this.hits.length ) % this.hits.length;
      if ( event.shiftKey ) this.picked.add( this.active );
      this.drawHits();
    } else if ( event.key === "Enter" ) {
      event.preventDefault();
      if ( !open ) return;
      if ( this.picked.size > 1 ) this.addPicked();
      else if ( this.active >= 0 ) this.addHits( [ this.active ] );
    } else if ( event.key === "Escape" ) {
      this.closeHits();
    }
  },

  addPicked() {
    return this.addHits( Array.from( this.picked ).sort( ( a , b ) => a - b ) );
  },

  // Adds hits as one change: each with its tags, at its position if it has
  // one. Papers already on the list are shown rather than refused.
  async addHits( indexes ) {
    const papers = indexes.map( ( index ) => this.hits[ index ] ).filter( Boolean );
    const fresh = papers.filter( ( paper ) => !this.positions.has( paper.key ) );
    if ( fresh.length === 0 ) {
      if ( papers[ 0 ] ) BoardView.flash( Dom.get( "list-rows" ) , papers[ 0 ].key );
      return;
    }
    const ops = [];
    const back = [];
    fresh.forEach( ( paper ) => {
      const tags = paper.addTags.map( ( name ) => this.createTag( name , ops , back ) );
      const op = { op: "add" , paper: paper.key };
      if ( tags.length ) op.tags = tags;
      const at = parseInt( paper.at , 10 );
      if ( Number.isFinite( at ) && at > 0 ) op.at = at;
      ops.push( op );
    } );
    back.unshift( { op: "remove" , rows: fresh.map( ( paper ) => paper.key ) } );
    const added = new Set( fresh.map( ( paper ) => paper.key ) );
    const done = await this.change( fresh.length > 1 ? "undo.list_add_many" : "undo.list_add" , ops , back , { flash: fresh[ 0 ].key } );
    if ( !done ) return;
    if ( this.hitsKind === "recent" ) {
      // Recently added lists what is NOT on the list: what was added goes.
      this.hits = this.hits.filter( ( paper ) => !added.has( paper.key ) );
      this.recentTotal = Math.max( 0 , this.recentTotal - added.size );
      Dom.text( Dom.get( "list-add-head" ) , this.recentHead() );
      this.picked = new Set();
      this.active = Math.min( this.active , this.hits.length - 1 );
      this.drawHits();
    } else {
      Dom.get( "list-add" ).value = "";
      this.closeHits();
    }
  },

  // ---- live ------------------------------------------------------------------

  listen() {
    if ( this.stream || typeof EventSource === "undefined" ) return;
    this.stream = true;
    Live.on( "/api/lists/stream" , "list" , ( event ) => {
      let data;
      try {
        data = JSON.parse( event.data );
      } catch ( error ) {
        return;
      }
      if ( data.deleted || data.renamed_from ) {
        // The open list went to the trash, or moved: follow it (or leave it).
        const mine = this.slug === data.slug || this.slug === data.renamed_from;
        if ( mine && data.deleted && data.by !== this.me.display_name ) {
          Dom.toast( I18n.get( "lists.list_deleted_by" ).replace( "{by}" , () => data.by ) , "error" );
        }
        this.loadLists( mine && !data.deleted ? data.slug : undefined ).catch( () => {} );
        return;
      }
      if ( !this.lists.some( ( list ) => list.slug === data.slug ) ) {
        // A list made (or put back) somewhere else: offer it in the picker.
        this.loadLists().catch( () => {} );
        return;
      }
      if ( data.slug !== this.slug || !this.view ) return;
      if ( data.locked !== undefined && data.locked !== this.view.locked ) {
        // View-only switched, here or in another tab: every row changes.
        this.view.locked = data.locked;
        this.draw();
        if ( data.by && data.by !== this.me.display_name ) {
          this.state( "" , I18n.get( data.locked ? "lists.locked_by" : "lists.unlocked_by" ).replace( "{by}" , () => data.by ) );
        }
        return;
      }
      if ( data.rev <= this.view.rev ) return;
      if ( this.sending > 0 ) {
        this.heard = Math.max( this.heard , data.rev );
        return;
      }
      this.open( data.slug ).then( () => {
        if ( data.by && data.by !== this.me.display_name ) {
          this.state( "" , I18n.get( "lists.changed_by" ).replace( "{by}" , () => data.by ) );
        }
      } ).catch( () => {} );
    } );
  },
};
