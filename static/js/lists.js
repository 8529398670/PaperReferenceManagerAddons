// The Lists screen (named Library in the sidebar): hand-ordered, tagged lists
// of papers.
//
// The picker's first entry, Library (#lists/library), is the built-in list
// of every paper in Zotero, newest added first. The server makes it from the
// catalogue (app/boards/service.py library_record); it is drawn like any other
// list but read-only, and each row has an Add button that copies the paper to
// another list (top, bottom or a position). It is the default.
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
  // The built-in Library list's slug. Reserved, so no stored list can take it
  // (app/boards/store.py RESERVED).
  LIBRARY: "library",
  me: null,
  lists: [],
  slug: null,
  paperContext: { slug: "" , name: "" , keys: [] },
  view: null,
  items: new Map(),
  positions: new Map(),
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
    // The Library list is Zotero: when papers come or go, fetch it again.
    Content.on( "changed" , () => {
      if ( this.slug === this.LIBRARY ) this.refreshLibrary();
    } );
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
    // Library first: it is always there, so the screen always has a list.
    const picker = Dom.get( "list-picker" );
    picker.replaceChildren(
      Dom.el( "option" , { text: I18n.get( "lists.library_entry" ) , attrs: { value: this.LIBRARY } } ),
      ...this.lists.map( ( list ) => Dom.el( "option" , { text: list.name , attrs: { value: list.slug } } ) ),
    );
    Dom.show( Dom.get( "list-menu-holder" ) , true );
    Dom.show( Dom.get( "lists-none" ) , this.lists.length === 0 );
    Dom.show( Dom.get( "list-body" ) , true );
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
    // Library is the default: a fresh load opens it, unless a link names a list.
    const known = ( slug ) => slug === this.LIBRARY || this.lists.some( ( list ) => list.slug === slug );
    const wanted = [ choose , linked , this.slug ].find( ( slug ) => slug && known( slug ) );
    await this.open( wanted || this.LIBRARY );
  },

  // Fetch the Library list again, at most every two seconds however many
  // lists change at once (a shared edit reaches several).
  refreshLibrary() {
    if ( this.libraryTimer ) return;
    this.libraryTimer = setTimeout( () => {
      this.libraryTimer = null;
      if ( this.slug === this.LIBRARY ) this.open( this.LIBRARY ).catch( () => {} );
    } , 2000 );
  },

  // The open list is the built-in Library: read-only, its rows added elsewhere.
  builtin() {
    return Boolean( this.view && this.view.builtin );
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
    // Not on the Library: it is never editable, so there is nothing to say.
    Dom.show( Dom.get( "list-view-only" ) , view.locked && !view.builtin );
    Dom.get( "lists-panel" ).classList.toggle( "is-locked" , Boolean( view.locked ) );
    const columns = this.columns();
    const colSig = ( view.builtin ? "adds|" : "" ) + columns.map( ( column ) => column.id + "=" + column.label ).join( "|" );
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
      doc: doc , papers: view.papers || {} , handlers: handlers , locked: view.locked , adds: Boolean( view.builtin ) ,
      recent: view.builtin ? ListManage.recent().map( ( list ) => ( { slug: list.slug , name: list.name } ) ) : [] , columns: columns ,
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
      addNear: ( indexes , anchor , side ) => this.addNear( indexes , anchor , side ),
      remove: ( key ) => this.remove( key ),
      addTo: ( key ) => ListManage.copyTo( ListManage.rowsFor( key ) ),
      quickAdd: ( key , slug ) => ListManage.quickAdd( key , slug ),
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
  //
  // As the old app's hits list had it: each hit not on the list yet has tags
  // to arrive with (chips), a # for where it goes (empty: the "add to…"
  // setting beside Recently added), and ＋ Add. Enter or a double-click adds
  // too; Cmd/Ctrl-click and Shift-click pick several, and then a tag, ＋ Add
  // or a drag goes for all of them. A hit can be dragged onto a row to land
  // right there. An added hit stays, as ✓ #n, so the reader keeps their place.

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
    Dom.get( "list-add-results" ).addEventListener( "scroll" , ( event ) => {
      const list = event.currentTarget;
      if ( list.scrollTop + list.clientHeight > list.scrollHeight - 240 ) this.moreRecent();
    } , { passive: true } );
    Dom.onPress( Dom.get( "list-add-picked" ) , () => this.addPicked() );
    Dom.get( "list-add-close" ).addEventListener( "click" , () => this.closeHits() );
    // Open while the pointer or the focus is in it: the hits have boxes of
    // their own (a tag, a position) to type in. Not while a hit is being
    // dragged onto the list below.
    document.addEventListener( "mousedown" , ( event ) => {
      if ( !Dom.get( "list-add-wrap" ).contains( event.target ) ) this.closeHits();
    } );
    Dom.get( "list-add-wrap" ).addEventListener( "focusout" , ( event ) => {
      if ( event.relatedTarget && !Dom.get( "list-add-wrap" ).contains( event.relatedTarget ) ) this.closeHits();
    } );
    // A paper saved into Zotero while Recently added is open shows up in it.
    Content.on( "changed" , () => this.freshRecent() );
  },

  hitsOpen() {
    return !Dom.get( "list-add-panel" ).hidden;
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

  // Every paper not on the list, newest in Zotero first, a page at a time:
  // scrolling to the foot of the panel (or arrowing down to it) brings more.
  async recent() {
    const ticket = ++this.addTicket;
    const answer = await this.recentPage( 0 );
    if ( ticket !== this.addTicket ) return;
    this.recentTotal = answer.total;
    this.recentNext = answer.next;
    this.recentOn = answer.on_list || 0;
    this.showHits( "recent" , answer.papers , this.recentHead() );
    Dom.get( "list-add-results" ).scrollTop = 0;
  },

  recentPage( offset ) {
    const params = new URLSearchParams( { not_on: this.slug , limit: String( this.recentChunk ) , offset: String( offset ) } );
    return Api.request( "/api/papers/recent?" + params );
  },

  recentChunk: 50,

  hit( paper ) {
    return Object.assign( {} , paper , { addTags: [] , at: "" , draft: "" } );
  },

  async moreRecent() {
    if ( this.hitsKind !== "recent" || this.recentNext == null || this.recentLoading ) return;
    if ( !this.hitsOpen() ) return;
    const ticket = this.addTicket;
    this.recentLoading = true;
    const list = Dom.get( "list-add-results" );
    const wait = Dom.el( "li" , { class: "list-group-item text-body-secondary small" , text: I18n.get( "lists.recent_more" ) } );
    list.appendChild( wait );
    try {
      const answer = await this.recentPage( this.recentNext );
      if ( ticket !== this.addTicket || this.hitsKind !== "recent" ) return;
      this.recentNext = answer.next;
      this.recentTotal = answer.total;
      this.recentOn = answer.on_list || 0;
      Dom.text( Dom.get( "list-add-head" ) , this.recentHead() );
      const have = new Set( this.hits.map( ( paper ) => paper.key ) );
      const start = this.hits.length;
      answer.papers.filter( ( paper ) => !have.has( paper.key ) ).forEach( ( paper ) => this.hits.push( this.hit( paper ) ) );
      // Added below what is there, so the reader's place does not move.
      const rows = [];
      for ( let at = start ; at < this.hits.length ; at++ ) rows.push( this.hitRow( this.hits[ at ] , at ) );
      wait.remove();
      list.append( ...rows );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    } finally {
      wait.remove();
      this.recentLoading = false;
    }
  },

  // The library changed: anything newer than the top hit goes in at the top,
  // and what was picked or typed stays with its paper.
  async freshRecent() {
    if ( this.hitsKind !== "recent" || !this.hitsOpen() || this.recentLoading ) return;
    const ticket = this.addTicket;
    let answer;
    try {
      answer = await this.recentPage( 0 );
    } catch ( error ) {
      return;
    }
    if ( ticket !== this.addTicket || this.hitsKind !== "recent" || !this.hitsOpen() ) return;
    const have = new Set( this.hits.map( ( paper ) => paper.key ) );
    const fresh = [];
    for ( const paper of answer.papers ) {
      if ( have.has( paper.key ) ) break;
      fresh.push( this.hit( paper ) );
    }
    this.recentTotal = answer.total;
    this.recentOn = answer.on_list || 0;
    if ( fresh.length ) {
      const n = fresh.length;
      this.hits = fresh.concat( this.hits );
      this.picked = new Set( Array.from( this.picked , ( index ) => index + n ) );
      if ( this.active >= 0 ) this.active += n;
      if ( this.pickAnchor >= 0 ) this.pickAnchor += n;
      if ( this.recentNext != null ) this.recentNext += n;
      this.drawHits( this.focusSpot() );
    }
    Dom.text( Dom.get( "list-add-head" ) , this.recentHead() );
  },

  recentHead() {
    return I18n.get( "lists.recent_head" ).replace( "{count}" , this.recentTotal ).replace( "{on}" , this.recentOn || 0 );
  },

  showHits( kind , papers , head ) {
    this.hitsKind = kind;
    this.hits = papers.map( ( paper ) => this.hit( paper ) );
    this.picked = new Set();
    this.active = this.hits.length ? 0 : -1;
    this.pickAnchor = this.active;
    Dom.text( Dom.get( "list-add-head" ) , head );
    Dom.show( Dom.get( "list-add-head" ) , Boolean( head ) );
    this.drawHits();
  },

  // Which box of which hit has the focus, to give it back after a redraw.
  focusSpot() {
    const focused = document.activeElement;
    const row = focused && focused.closest && focused.closest( "#list-add-results .add-hit" );
    if ( !row || !focused.getAttribute( "data-hit-box" ) ) return null;
    return { key: row.getAttribute( "data-key" ) , box: focused.getAttribute( "data-hit-box" ) };
  },

  drawHits( focus ) {
    const list = Dom.get( "list-add-results" );
    const top = list.scrollTop;
    const items = this.hits.map( ( paper , index ) => this.hitRow( paper , index ) );
    if ( items.length === 0 ) {
      items.push( Dom.el( "li" , { class: "list-group-item text-body-secondary" , text: I18n.get( this.hitsKind === "recent" ? "lists.recent_nothing" : "lists.add_nothing" ) } ) );
    }
    list.replaceChildren( ...items );
    list.scrollTop = top;
    const button = Dom.get( "list-add-picked" );
    const waiting = Array.from( this.picked ).filter( ( index ) => this.hits[ index ] && !this.positions.has( this.hits[ index ].key ) );
    Dom.show( button , waiting.length > 1 );
    Dom.text( button , I18n.get( "lists.add_picked" ).replace( "{count}" , waiting.length ) );
    Dom.show( Dom.get( "list-add-panel" ) , true );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "true" );
    if ( focus ) {
      const row = list.querySelector( '.add-hit[data-key="' + CSS.escape( focus.key ) + '"]' );
      const box = row && row.querySelector( '[data-hit-box="' + focus.box + '"]' );
      if ( box ) {
        box.focus();
        if ( box.setSelectionRange && typeof box.value === "string" ) box.setSelectionRange( box.value.length , box.value.length );
        return;
      }
    }
    const active = list.querySelector( ".add-hit.active" );
    if ( active && !focus ) {
      const view = list.getBoundingClientRect();
      const box = active.getBoundingClientRect();
      if ( box.top < view.top ) list.scrollTop -= view.top - box.top;
      else if ( box.bottom > view.bottom ) list.scrollTop += box.bottom - view.bottom;
    }
  },

  // The hits an action on hit index acts on: every picked one when it is
  // among several picked, else just it.
  group( index ) {
    return this.picked.has( index ) && this.picked.size > 1 ? Array.from( this.picked ).sort( ( a , b ) => a - b ) : [ index ];
  },

  // "added 3h ago": how long ago, which is all anyone reads of the stamp.
  // The catalogue's stamps are UTC without a zone.
  ago( stamp ) {
    const time = Date.parse( String( stamp || "" ).replace( " " , "T" ) + "Z" );
    if ( !time ) return "";
    const minutes = Math.max( 0 , ( Date.now() - time ) / 60000 );
    let when;
    if ( minutes < 2 ) when = I18n.get( "lists.ago_now" );
    else if ( minutes < 60 ) when = I18n.get( "lists.ago_minutes" ).replace( "{n}" , Math.round( minutes ) );
    else if ( minutes < 1440 ) when = I18n.get( "lists.ago_hours" ).replace( "{n}" , Math.round( minutes / 60 ) );
    else if ( minutes < 43200 ) when = I18n.get( "lists.ago_days" ).replace( "{n}" , Math.round( minutes / 1440 ) );
    else when = String( stamp ).slice( 0 , 10 );
    return I18n.get( "lists.added_ago" ).replace( "{when}" , when );
  },

  hitRow( paper , index ) {
    const on = this.positions.get( paper.key );
    const picked = this.picked.has( index );
    const meta = [ PaperLinks.meta( paper ) ];
    if ( this.hitsKind === "recent" && paper.added ) meta.push( this.ago( paper.added ) );
    const children = [
      Dom.el( "div" , { class: "paper-title" , text: paper.title } ),
      Dom.el( "div" , { class: "paper-meta" , text: meta.filter( Boolean ).join( " · " ) } ),
    ];
    if ( paper.content !== undefined ) children.push( Content.strip( paper.key , paper.content ) );
    const locked = Boolean( this.view && this.view.locked );
    if ( on ) {
      children.push( Dom.el( "div" , { class: "small text-success fw-semibold" , children: [
        Dom.el( "i" , { class: "bi bi-check2 me-1" , attrs: { "aria-hidden": "true" } } ),
        Dom.el( "span" , { text: I18n.get( "lists.add_on_list" ).replace( "{n}" , on ) } ),
      ] } ) );
    } else if ( !locked ) {
      children.push( Dom.el( "div" , { class: "d-flex flex-wrap align-items-center column-gap-3 row-gap-1 mt-1" , children: [
        this.hitTags( paper , index ) , this.hitControls( paper , index ),
      ] } ) );
    }
    const element = Dom.el( "li" , {
      class: "list-group-item list-group-item-action add-hit" + ( index === this.active ? " active" : "" ) + ( picked ? " is-picked" : "" ),
      attrs: { role: "option" , "aria-selected": String( picked || index === this.active ) , "data-key": paper.key },
      children: children,
    } );
    element.addEventListener( "mousedown" , ( event ) => {
      if ( event.target.closest( "input, button, a" ) ) return;
      // Not the input's blur first.
      event.preventDefault();
      this.pickHit( index , event );
    } );
    element.addEventListener( "dblclick" , ( event ) => {
      if ( event.target.closest( "input, button, a" ) ) return;
      this.addHits( [ index ] );
    } );
    if ( !on && !locked ) this.hitDraggable( element , index );
    return element;
  },

  // The tags it will arrive with, as chips, and a box to type another in.
  // Enter with text adds the tag (to every picked hit, when this is one of
  // several); Enter on an empty box adds the paper.
  hitTags( paper , index ) {
    const vocab = ( this.view.doc.vocab && this.view.doc.vocab.tags ) || [];
    const chips = paper.addTags.map( ( name ) => {
      const chip = Dom.el( "span" , { class: "tag-chip" , children: [ Dom.el( "span" , { text: name } ) ] } );
      TagColors.paint( chip , name , vocab );
      chip.appendChild( Dom.el( "button" , {
        class: "tag-chip-remove",
        attrs: { type: "button" , "aria-label": I18n.get( "lists.tag_unadd" ).replace( "{tag}" , () => name ) },
        text: "×",
        on: { click: () => {
          paper.addTags = paper.addTags.filter( ( tag ) => tag.toLowerCase() !== name.toLowerCase() );
          this.drawHits();
        } },
      } ) );
      return chip;
    } );
    const input = Dom.el( "input" , {
      class: "form-control form-control-sm tag-input",
      attrs: {
        type: "text" , list: "list-tag-options" , autocomplete: "off" , draggable: "false" , "data-hit-box": "tag",
        placeholder: I18n.get( "lists.tag_add_placeholder" ),
        title: I18n.get( "lists.hit_tag_help" ),
        "aria-label": BoardView.label( "lists.tag_add_label" , paper.title ),
      },
    } );
    input.value = paper.draft;
    input.addEventListener( "input" , () => { paper.draft = input.value; } );
    input.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      const names = input.value.split( "," ).map( ( name ) => name.trim() ).filter( Boolean );
      if ( names.length === 0 ) {
        this.addHits( this.group( index ) );
        return;
      }
      this.group( index ).forEach( ( at ) => {
        const hit = this.hits[ at ];
        hit.draft = "";
        names.forEach( ( name ) => {
          if ( !hit.addTags.some( ( tag ) => tag.toLowerCase() === name.toLowerCase() ) ) hit.addTags.push( name );
        } );
      } );
      this.drawHits( { key: paper.key , box: "tag" } );
    } );
    return Dom.el( "div" , { class: "board-row-tags" , children: chips.concat( [ input ] ) } );
  },

  // Where it goes and the button that puts it there.
  hitControls( paper , index ) {
    const at = Dom.el( "input" , {
      class: "form-control form-control-sm board-row-num",
      attrs: {
        type: "text" , inputmode: "numeric" , autocomplete: "off" , draggable: "false" , "data-hit-box": "at",
        placeholder: "#" , title: I18n.get( "lists.add_at_help" ),
        "aria-label": BoardView.label( "lists.add_at_label" , paper.title ),
      },
    } );
    at.value = paper.at;
    at.addEventListener( "input" , () => { paper.at = at.value.trim(); } );
    at.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      this.addHits( this.group( index ) );
    } );
    const count = this.group( index ).filter( ( i ) => this.hits[ i ] && !this.positions.has( this.hits[ i ].key ) ).length;
    const button = Dom.el( "button" , {
      class: "btn btn-sm btn-primary",
      attrs: { type: "button" , "data-hit-box": "add" , title: I18n.get( "lists.add_button_help" ) },
      text: count > 1 ? I18n.get( "lists.add_picked" ).replace( "{count}" , count ) : I18n.get( "lists.add_one" ),
      on: { click: () => this.addHits( this.group( index ) ) },
    } );
    return Dom.el( "div" , { class: "add-hit-extra align-items-center mt-0" , children: [ at , button ] } );
  },

  // Dragged onto a row of the list, it lands right there (BoardView.draggable
  // takes the drop); several picked go together.
  hitDraggable( element , index ) {
    element.draggable = true;
    element.addEventListener( "dragstart" , ( event ) => {
      if ( event.target.closest && event.target.closest( "input" ) ) {
        event.preventDefault();
        return;
      }
      const indexes = this.group( index ).filter( ( i ) => this.hits[ i ] && !this.positions.has( this.hits[ i ].key ) );
      BoardView.dragging = { add: indexes };
      this.hitDragging = true;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData( "text/plain" , this.hits[ index ].key );
    } );
    element.addEventListener( "dragend" , () => {
      BoardView.dragging = null;
      this.hitDragging = false;
      Dom.all( ".drop-before, .drop-after, .drop-into" ).forEach( ( row ) => row.classList.remove( "drop-before" , "drop-after" , "drop-into" ) );
    } );
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
    if ( this.hitDragging ) return;
    Dom.show( Dom.get( "list-add-panel" ) , false );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "false" );
  },

  onAddKey( event ) {
    const open = this.hitsOpen();
    if ( event.key === "ArrowDown" || event.key === "ArrowUp" ) {
      if ( !open || !this.hits.length ) return;
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      this.active = ( this.active + step + this.hits.length ) % this.hits.length;
      if ( event.shiftKey ) this.picked.add( this.active );
      this.drawHits();
      if ( this.active >= this.hits.length - 5 ) this.moreRecent();
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

  // What a hit's # box says: a position, "top" / "bottom", or nothing (the
  // "add to…" setting).
  hitAt( text ) {
    const value = String( text || "" ).trim().toLowerCase();
    if ( !value ) return undefined;
    if ( value === "top" || value === "t" ) return "top";
    if ( value === "bottom" || value === "b" ) return "bottom";
    const at = parseInt( value.replace( /^#/ , "" ) , 10 );
    return Number.isFinite( at ) && at > 0 ? at : undefined;
  },

  // Dropped on a row: before or after it, in the order they were listed.
  addNear( indexes , anchor , side ) {
    // Onto the list's own rows only (not the shelf's).
    if ( !this.positions.has( anchor ) ) return undefined;
    return this.addHits( indexes , { anchor: anchor , side: side } );
  },

  // Adds hits as one change: each with its tags (and any tag still typed in
  // its box), at its position if it has one, or next to a row they were
  // dropped on. Papers already on the list are shown rather than refused.
  async addHits( indexes , near ) {
    const papers = indexes.map( ( index ) => this.hits[ index ] ).filter( Boolean );
    const fresh = papers.filter( ( paper ) => !this.positions.has( paper.key ) );
    if ( fresh.length === 0 ) {
      if ( papers[ 0 ] ) BoardView.flash( Dom.get( "list-rows" ) , papers[ 0 ].key );
      return;
    }
    const ops = [];
    const back = [];
    let previous = null;
    fresh.forEach( ( paper ) => {
      const typed = paper.draft.split( "," ).map( ( name ) => name.trim() ).filter( Boolean );
      const names = paper.addTags.concat( typed.filter( ( name ) => !paper.addTags.some( ( tag ) => tag.toLowerCase() === name.toLowerCase() ) ) );
      const tags = names.map( ( name ) => this.createTag( name , ops , back ) );
      const op = { op: "add" , paper: paper.key };
      if ( tags.length ) op.tags = tags;
      if ( near ) {
        // Before the row: each lands in front of it, so they keep their order.
        // After it: each after the one before.
        op.at = near.side === "before" ? { before: near.anchor } : { after: previous || near.anchor };
        previous = paper.key;
      } else {
        const at = this.hitAt( paper.at );
        if ( at !== undefined ) op.at = at;
      }
      ops.push( op );
    } );
    back.unshift( { op: "remove" , rows: fresh.map( ( paper ) => paper.key ) } );
    const focus = this.focusSpot();
    const done = await this.change( fresh.length > 1 ? "undo.list_add_many" : "undo.list_add" , ops , back , { flash: fresh[ 0 ].key } );
    if ( !done ) return;
    fresh.forEach( ( paper ) => {
      paper.draft = "";
      paper.addTags = [];
      paper.at = "";
    } );
    if ( this.hitsKind === "recent" ) {
      // The server leaves out what is on the list, so its pages shift up by
      // what was added; here the added ones stay, as ✓ #n.
      this.recentTotal = Math.max( 0 , this.recentTotal - fresh.length );
      this.recentOn = ( this.recentOn || 0 ) + fresh.length;
      if ( this.recentNext != null ) this.recentNext = Math.max( 0 , this.recentNext - fresh.length );
      Dom.text( Dom.get( "list-add-head" ) , this.recentHead() );
    }
    this.picked = new Set();
    if ( this.hitsOpen() ) this.drawHits( focus );
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
      // The Library shows what every list says about each paper.
      if ( this.slug === this.LIBRARY && this.sending === 0 ) this.refreshLibrary();
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
