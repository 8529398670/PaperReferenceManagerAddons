// The Lists screen: hand-ordered, tagged lists of papers.
//
// Every change is a batch of ops sent to POST /api/lists/<slug>/ops (the same
// ops an API key or an MCP agent sends; app/boards/ops.py has them all). The
// answer carries the list as it now is, which is drawn as it comes. There is
// no whole-list save, so there is nothing to merge and no draft to keep: what
// is on screen is what the server has.
//
// Every change is undoable: each one is sent through Undo.run with the ops
// that put it back, worked out before it is sent.
//
// Live: /api/lists/stream says "list X is at rev N" whenever any list changes,
// from another tab, another person or an agent; the open list is fetched again
// when that is newer than what is showing.
const Lists = {
  me: null,
  lists: [],
  slug: null,
  view: null,
  storageKey: "lists-open",
  addTimer: null,
  addTicket: 0,
  addHits: [],
  addActive: -1,
  stream: null,
  // Changes this page has sent and not heard back about. While there are any,
  // a live "the list moved" is most likely the echo of one of them, and is
  // held until they are answered (heard).
  sending: 0,
  heard: 0,
  claimedColors: new Set(),

  async init( me ) {
    this.me = me;
    Dom.show( Dom.get( "lists-panel" ) , true );
    Dom.get( "list-picker" ).addEventListener( "change" , ( event ) => this.open( event.target.value ) );
    Dom.get( "list-new" ).addEventListener( "click" , () => this.showNewForm( true ) );
    Dom.get( "list-new-cancel" ).addEventListener( "click" , () => this.showNewForm( false ) );
    Dom.onSubmit( Dom.get( "list-new-form" ) , this.onCreate.bind( this ) );
    Dom.get( "list-filter" ).addEventListener( "input" , () => this.draw() );
    const add = Dom.get( "list-add" );
    add.addEventListener( "input" , () => this.searchLater() );
    add.addEventListener( "keydown" , ( event ) => this.onAddKey( event ) );
    add.addEventListener( "blur" , () => setTimeout( () => this.closeHits() , 150 ) );
    await this.loadLists();
    this.listen();
  },

  // ---- which list -------------------------------------------------------

  remembered() {
    try {
      return window.localStorage.getItem( this.storageKey ) || "";
    } catch ( error ) {
      return "";
    }
  },

  remember( slug ) {
    try {
      window.localStorage.setItem( this.storageKey , slug );
    } catch ( error ) { /* only a convenience */ }
  },

  async loadLists( choose ) {
    const answer = await Api.request( "/api/lists?limit=1000" );
    this.lists = answer.lists;
    const picker = Dom.get( "list-picker" );
    picker.replaceChildren( ...this.lists.map( ( list ) => Dom.el( "option" , { text: list.name , attrs: { value: list.slug } } ) ) );
    Dom.show( picker , this.lists.length > 0 );
    Dom.show( Dom.get( "lists-none" ) , this.lists.length === 0 );
    Dom.show( Dom.get( "list-body" ) , this.lists.length > 0 );
    if ( this.lists.length === 0 ) {
      this.view = null;
      Dom.text( Dom.get( "list-count" ) , "" );
      return;
    }
    const wanted = [ choose , this.slug , this.remembered() , "main" ].find( ( slug ) => slug && this.lists.some( ( list ) => list.slug === slug ) );
    await this.open( wanted || this.lists[ 0 ].slug );
  },

  async open( slug ) {
    const answer = await Api.request( "/api/lists/" + encodeURIComponent( slug ) );
    this.slug = slug;
    this.remember( slug );
    Dom.get( "list-picker" ).value = slug;
    this.view = answer.list;
    this.draw();
  },

  showNewForm( visible ) {
    Dom.show( Dom.get( "list-new-form" ) , visible );
    if ( visible ) Dom.get( "list-new-name" ).focus();
  },

  async onCreate( event ) {
    event.preventDefault();
    const name = Dom.get( "list-new-name" ).value.trim();
    if ( !name ) return;
    try {
      const answer = await Api.post( "/api/lists" , { name: name } );
      Dom.get( "list-new-name" ).value = "";
      this.showNewForm( false );
      await this.loadLists( answer.list.slug );
      Dom.toast( I18n.get( "ui.saved" ) , "ok" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  // ---- drawing -------------------------------------------------------------

  draw() {
    const view = this.view;
    if ( !view ) return;
    const doc = view.doc;
    const count = ( doc.items || [] ).length;
    Dom.text( Dom.get( "list-count" ) , I18n.get( "lists.count" ).replace( "{count}" , count.toLocaleString() ) );
    Dom.show( Dom.get( "list-view-only" ) , view.locked );
    const filter = Dom.get( "list-filter" ).value;
    const handlers = {
      move: ( key , position ) => this.move( key , position ),
      moveNear: ( key , anchor , side ) => this.moveNear( key , anchor , side ),
      remove: ( key ) => this.remove( key ),
      addTag: ( key , name ) => this.addTag( key , name ),
      removeTag: ( key , name ) => this.removeTag( key , name ),
      setNote: ( key , value , previous ) => this.setNote( key , value , previous ),
    };
    const rows = Dom.get( "list-rows" );
    const focus = this.focusOf( rows );
    const shown = BoardView.render( rows , doc , view.papers || {} , handlers , filter , view.locked );
    this.restoreFocus( rows , focus );
    const filtered = Dom.get( "list-filtered" );
    Dom.text( filtered , I18n.get( "lists.filtered" ).replace( "{shown}" , shown ).replace( "{count}" , count ) );
    Dom.show( filtered , filter.trim() !== "" );
    Dom.show( Dom.get( "list-empty" ) , count === 0 );
    const options = Dom.get( "list-tag-options" );
    options.replaceChildren( ...( ( doc.vocab && doc.vocab.tags ) || [] ).map( ( tag ) => Dom.el( "option" , { attrs: { value: tag.name } } ) ) );
  },

  // A redraw replaces every row. Whatever field had the focus (a note being
  // typed in, the next tag box) gets it back, with its caret and anything
  // typed there that was not sent yet.
  focusOf( rows ) {
    const active = document.activeElement;
    if ( !active || !rows.contains( active ) ) return null;
    const row = active.closest( "[data-key]" );
    const kind = [ "board-row-note" , "tag-input" , "board-row-num" ].find( ( name ) => active.classList.contains( name ) );
    if ( !row || !kind ) return null;
    return { key: row.getAttribute( "data-key" ) , kind: kind , value: active.value , start: active.selectionStart , end: active.selectionEnd };
  },

  restoreFocus( rows , focus ) {
    if ( !focus ) return;
    const row = Array.from( rows.children ).find( ( element ) => element.getAttribute( "data-key" ) === focus.key );
    const field = row && row.querySelector( "." + focus.kind );
    if ( !field ) return;
    if ( focus.kind !== "board-row-num" ) field.value = focus.value;
    field.focus();
    try {
      field.setSelectionRange( focus.start , focus.end );
    } catch ( error ) { /* not every field has a caret */ }
  },

  state( key ) {
    Dom.text( Dom.get( "list-state" ) , key ? I18n.get( key ) : "" );
  },

  // ---- sending ---------------------------------------------------------------

  // Sends a batch to the open list, draws the answer. The slug is fixed at the
  // time of the action, so an undo reaches the list it happened on even after
  // another one was opened.
  async send( slug , ops ) {
    this.state( "lists.saving" );
    this.sending += 1;
    try {
      const answer = await Api.post( "/api/lists/" + encodeURIComponent( slug ) + "/ops" , { ops: ops } );
      if ( slug === this.slug && answer.list ) {
        this.view = answer.list;
        this.draw();
      }
      this.state( "lists.saved" );
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

  // One undoable change: ops now, back() to put it back.
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
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      // What is on screen may be ahead of the server now: ask again.
      if ( slug === this.slug ) await this.open( slug ).catch( () => {} );
    }
  },

  item( key ) {
    const items = ( this.view && this.view.doc.items ) || [];
    const index = items.findIndex( ( item ) => item.key === key );
    return index < 0 ? null : { index: index , item: items[ index ] };
  },

  move( key , position ) {
    const found = this.item( key );
    if ( !found ) return;
    this.change( "undo.list_move" , [ { op: "move" , row: key , to: position } ] , [ { op: "move" , row: key , to: found.index + 1 } ] , { flash: key } );
  },

  moveNear( key , anchor , side ) {
    const found = this.item( key );
    if ( !found ) return;
    const to = {};
    to[ side ] = anchor;
    this.change( "undo.list_move" , [ { op: "move" , row: key , to: to } ] , [ { op: "move" , row: key , to: found.index + 1 } ] , { flash: key } );
  },

  remove( key ) {
    const found = this.item( key );
    if ( !found ) return;
    const item = found.item;
    // Everything the row was, so putting it back loses nothing: its tags, its
    // cells, where it stood.
    const paper = { key: item.key , title: item.title || "" , doi: item.doi || "" , year: item.year || null , journal: item.journal || "" };
    if ( item.authors ) paper.authors = item.authors;
    const back = [ {
      op: "add" , paper: paper , at: found.index + 1 , tags: item.tags || [] ,
      cells: item.fields || {} , auto_tag: false , prefill: false ,
    } ];
    this.change( "undo.list_remove" , [ { op: "remove" , rows: [ key ] } ] , back , { toast: true } );
  },

  addTag( key , name ) {
    const found = this.item( key );
    if ( !found ) return;
    if ( ( found.item.tags || [] ).some( ( tag ) => tag.toLowerCase() === name.toLowerCase() ) ) return;
    const vocab = this.view.doc.vocab.tags || [];
    const known = vocab.find( ( tag ) => tag.name.toLowerCase() === name.toLowerCase() );
    const ops = [];
    const back = [ { op: "tag" , row: key , remove: [ known ? known.name : name ] } ];
    let color = null;
    if ( !known ) {
      // A new tag takes the next colour no tag has, nor one still on its way
      // to the server; undoing takes it off the list's tags again, since only
      // this row had it.
      color = TagColors.next( vocab.concat( Array.from( this.claimedColors , ( claimed ) => ( { color: claimed } ) ) ) );
      this.claimedColors.add( color );
      ops.push( { op: "tag_create" , name: name , color: color } );
      back.push( { op: "tag_delete" , name: name } );
    }
    ops.push( { op: "tag" , row: key , add: [ known ? known.name : name ] } );
    this.change( "undo.list_tag" , ops , back ).finally( () => {
      if ( color ) this.claimedColors.delete( color );
    } );
  },

  removeTag( key , name ) {
    this.change( "undo.list_tag" , [ { op: "tag" , row: key , remove: [ name ] } ] , [ { op: "tag" , row: key , add: [ name ] } ] );
  },

  setNote( key , value , previous ) {
    this.change( "undo.list_note" ,
      [ { op: "set_cell" , row: key , col: "notes" , value: value } ] ,
      [ { op: "set_cell" , row: key , col: "notes" , value: previous } ] );
  },

  // ---- adding from the library -------------------------------------------

  searchLater() {
    clearTimeout( this.addTimer );
    this.addTimer = setTimeout( () => this.search() , 150 );
  },

  async search() {
    const text = Dom.get( "list-add" ).value.trim();
    const ticket = ++this.addTicket;
    if ( text.length < 2 ) {
      this.closeHits();
      return;
    }
    const params = new URLSearchParams( { q: text , mode: "title" , limit: "8" } );
    const answer = await Api.request( "/api/papers?" + params );
    if ( ticket !== this.addTicket ) return;
    this.addHits = answer.papers;
    this.addActive = answer.papers.length ? 0 : -1;
    this.drawHits();
  },

  drawHits() {
    const list = Dom.get( "list-add-results" );
    const items = this.addHits.map( ( paper , index ) => {
      const on = this.item( paper.key );
      const children = [
        Dom.el( "div" , { class: "paper-title" , text: paper.title } ),
        Dom.el( "div" , { class: "paper-meta" , text: PaperLinks.meta( paper ) } ),
      ];
      if ( on ) children.push( Dom.el( "div" , { class: "small text-success" , text: I18n.get( "lists.add_on_list" ).replace( "{n}" , on.index + 1 ) } ) );
      const element = Dom.el( "li" , {
        class: "list-group-item list-group-item-action add-hit" + ( index === this.addActive ? " active" : "" ),
        attrs: { role: "option" , "aria-selected": String( index === this.addActive ) },
        children: children,
      } );
      // mousedown, not click: the input's blur would close the list first.
      element.addEventListener( "mousedown" , ( event ) => {
        event.preventDefault();
        this.pick( index );
      } );
      return element;
    } );
    if ( items.length === 0 ) items.push( Dom.el( "li" , { class: "list-group-item text-body-secondary" , text: I18n.get( "lists.add_nothing" ) } ) );
    list.replaceChildren( ...items );
    Dom.show( list , true );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "true" );
  },

  closeHits() {
    Dom.show( Dom.get( "list-add-results" ) , false );
    Dom.get( "list-add" ).setAttribute( "aria-expanded" , "false" );
  },

  onAddKey( event ) {
    const open = !Dom.get( "list-add-results" ).hidden;
    if ( event.key === "ArrowDown" || event.key === "ArrowUp" ) {
      if ( !open || !this.addHits.length ) return;
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      this.addActive = ( this.addActive + step + this.addHits.length ) % this.addHits.length;
      this.drawHits();
    } else if ( event.key === "Enter" ) {
      event.preventDefault();
      if ( open && this.addActive >= 0 ) this.pick( this.addActive );
    } else if ( event.key === "Escape" ) {
      this.closeHits();
    }
  },

  pick( index ) {
    const paper = this.addHits[ index ];
    if ( !paper || !this.view ) return;
    const on = this.item( paper.key );
    if ( on ) {
      // Already here: show it rather than refuse.
      this.closeHits();
      BoardView.flash( Dom.get( "list-rows" ) , paper.key );
      return;
    }
    Dom.get( "list-add" ).value = "";
    this.closeHits();
    this.change( "undo.list_add" , [ { op: "add" , paper: paper.key } ] , [ { op: "remove" , rows: [ paper.key ] } ] , { flash: paper.key } );
  },

  // ---- live ------------------------------------------------------------------

  listen() {
    if ( this.stream || typeof EventSource === "undefined" ) return;
    this.stream = new EventSource( "/api/lists/stream" );
    this.stream.addEventListener( "list" , ( event ) => {
      let data;
      try {
        data = JSON.parse( event.data );
      } catch ( error ) {
        return;
      }
      if ( !this.lists.some( ( list ) => list.slug === data.slug ) ) {
        // A list made somewhere else: offer it in the picker.
        this.loadLists().catch( () => {} );
        return;
      }
      if ( data.slug !== this.slug || !this.view || data.rev <= this.view.rev ) return;
      if ( this.sending > 0 ) {
        this.heard = Math.max( this.heard , data.rev );
        return;
      }
      this.open( data.slug ).then( () => {
        if ( data.by && data.by !== this.me.display_name ) {
          Dom.text( Dom.get( "list-state" ) , I18n.get( "lists.changed_by" ).replace( "{by}" , () => data.by ) );
        }
      } ).catch( () => {} );
    } );
  },
};
