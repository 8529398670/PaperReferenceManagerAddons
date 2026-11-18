// The Searches screen: saved searches, which replace the old searches/*.py
// files. A search is a name, a boolean query in the search box's grammar, and
// named groups of terms (any / all / none of them, or at least n of other
// groups). It runs over the library and the missing pool as it is edited, so
// the counts below the editor are always what Save would keep.
//
// The crawl (crawl.js) scores with a search's terms, and missing.xlsx writes a
// sheet for each.
const Searches = {
  list: [],
  current: null,
  groups: [],
  pool: "library",
  answer: null,
  ticket: 0,
  dirty: false,

  init() {
    Dom.show( Dom.get( "searches-panel" ) , true );
    Dom.onPress( Dom.get( "searches-new" ) , () => this.open( null ) );
    Dom.onPress( Dom.get( "search-add-group" ) , () => {
      this.groups.push( { name: this.freeName() , mode: "any" , terms: [] , required: true } );
      this.drawGroups();
      this.changed();
    } );
    Dom.onSubmit( Dom.get( "search-form" ) , ( event ) => {
      event.preventDefault();
      return this.save();
    } );
    Dom.onPress( Dom.get( "search-delete" ) , () => this.remove() );
    Dom.onPress( Dom.get( "search-add-all" ) , () => this.addAll() );
    [ "search-name" , "search-description" ].forEach( ( id ) => Dom.get( id ).addEventListener( "input" , () => { this.dirty = true; this.paintState(); } ) );
    Dom.typed( Dom.get( "search-query" ) , () => this.changed() , 400 );
    Dom.all( "[data-search-pool]" ).forEach( ( tab ) => tab.addEventListener( "click" , ( event ) => {
      event.preventDefault();
      this.pool = tab.getAttribute( "data-search-pool" );
      this.draw();
    } ) );
    this.table = new DataTable( {
      name: "search-results",
      holder: Dom.get( "search-results" ),
      menu: null,
      columns: this.columns(),
      sort: [ { col: "rank" , desc: false } ],
    } );
    window.addEventListener( "hashchange" , () => { if ( Nav.current() === "searches" && !this.loaded ) this.load(); } );
    if ( Nav.current() === "searches" ) this.load();
  },

  async load() {
    this.loaded = true;
    try {
      const answer = await Api.request( "/api/searches" );
      this.list = answer.searches;
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.drawList();
    const keep = this.current && this.list.find( ( s ) => s.id === this.current.id );
    this.open( keep || this.list[ 0 ] || null );
  },

  // The names the crawl's picker offers, kept fresh when they change here.
  async names() {
    if ( !this.loaded ) await this.load();
    return this.list;
  },

  drawList() {
    const holder = Dom.get( "searches-list" );
    Dom.clear( holder );
    Dom.show( Dom.get( "searches-empty" ) , this.list.length === 0 );
    this.list.forEach( ( search ) => {
      const active = this.current && this.current.id === search.id;
      const item = Dom.el( "button" , {
        class: "list-group-item list-group-item-action" + ( active ? " active" : "" ),
        attrs: { type: "button" , "aria-current": active ? "true" : "false" },
        children: [
          Dom.el( "div" , { class: "fw-semibold" , text: search.name } ),
          Dom.el( "div" , { class: "small text-truncate" + ( active ? "" : " text-body-secondary" ) , text: search.description || search.query || this.groupLine( search ) } ),
        ],
        on: { click: () => this.open( search ) },
      } );
      holder.appendChild( item );
    } );
    Nav.summary( "searches" , I18n.get( "searches.count" ).replace( "{n}" , this.list.length ) );
  },

  groupLine( search ) {
    return ( search.groups || [] ).map( ( g ) => g.name ).join( " · " );
  },

  freeName() {
    const used = new Set( this.groups.map( ( g ) => g.name ) );
    let n = this.groups.length + 1;
    while ( used.has( "GROUP_" + n ) ) n += 1;
    return "GROUP_" + n;
  },

  open( search ) {
    this.current = search;
    this.dirty = false;
    Dom.get( "search-name" ).value = search ? search.name : "";
    Dom.get( "search-description" ).value = search ? search.description || "" : "";
    Dom.get( "search-query" ).value = search ? search.query || "" : "";
    this.groups = search ? JSON.parse( JSON.stringify( search.groups || [] ) ) : [];
    Dom.show( Dom.get( "search-delete" ) , Boolean( search ) );
    this.problems( null );
    this.drawList();
    this.drawGroups();
    this.paintState();
    this.run();
  },

  paintState() {
    const text = !this.current ? I18n.get( "searches.state_new" ) : this.dirty ? I18n.get( "searches.state_unsaved" ) : "";
    Dom.text( Dom.get( "search-state" ) , text );
    const id = this.current && !this.dirty ? encodeURIComponent( this.current.id ) : "";
    [ [ "search-export-xlsx" , "xlsx" ] , [ "search-export-md" , "md" ] ].forEach( ( [ elementId , format ] ) => {
      const link = Dom.get( elementId );
      link.setAttribute( "href" , id ? "/api/searches/" + id + "/export?format=" + format : "#" );
      link.classList.toggle( "disabled" , !id );
      link.setAttribute( "aria-disabled" , String( !id ) );
    } );
  },

  // -- the groups editor --------------------------------------------------------------

  drawGroups() {
    const holder = Dom.get( "search-groups" );
    Dom.clear( holder );
    this.groups.forEach( ( group , index ) => holder.appendChild( this.groupCard( group , index ) ) );
  },

  groupCard( group , index ) {
    const id = "search-group-" + index;
    const name = Dom.el( "input" , { class: "form-control form-control-sm font-monospace" , attrs: { id: id + "-name" , value: group.name , maxlength: "40" , autocomplete: "off" } } );
    name.addEventListener( "change" , () => {
      const old = group.name;
      group.name = name.value.trim();
      this.groups.forEach( ( other ) => { if ( other.of ) other.of = other.of.map( ( n ) => ( n === old ? group.name : n ) ); } );
      this.drawGroups();
      this.changed();
    } );
    const mode = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { id: id + "-mode" } } );
    [ "any" , "all" , "none" , "at_least" ].forEach( ( value ) => mode.appendChild( Dom.el( "option" , { text: I18n.get( "searches.mode_" + value ) , attrs: { value: value } } ) ) );
    mode.value = group.mode;
    mode.addEventListener( "change" , () => {
      group.mode = mode.value;
      if ( group.mode === "at_least" ) {
        group.of = group.of || [];
        group.n = group.n || 1;
      } else group.terms = group.terms || [];
      this.drawGroups();
      this.changed();
    } );
    const required = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: id + "-required" } } );
    required.checked = group.required !== false;
    required.addEventListener( "change" , () => { group.required = required.checked; this.changed(); } );
    const remove = Dom.el( "button" , {
      class: "btn btn-outline-danger btn-sm",
      attrs: { type: "button" , title: I18n.get( "searches.remove_group" ) , "aria-label": I18n.get( "searches.remove_group" ) },
      children: [ Dom.el( "i" , { class: "bi bi-x-lg" , attrs: { "aria-hidden": "true" } } ) ],
      on: { click: () => { this.groups.splice( index , 1 ); this.drawGroups(); this.changed(); } },
    } );
    const count = this.tallyOf( group.name );
    const head = Dom.el( "div" , { class: "row g-2 align-items-center" , children: [
      Dom.el( "div" , { class: "col-12 col-md-4" , children: [ Dom.el( "label" , { class: "visually-hidden" , text: I18n.get( "searches.group_name" ) , attrs: { for: id + "-name" } } ) , name ] } ),
      Dom.el( "div" , { class: "col col-md-4" , children: [ Dom.el( "label" , { class: "visually-hidden" , text: I18n.get( "searches.group_mode" ) , attrs: { for: id + "-mode" } } ) , mode ] } ),
      Dom.el( "div" , { class: "col-auto" , children: [ Dom.el( "div" , { class: "form-check mb-0" , children: [ required , Dom.el( "label" , { class: "form-check-label small" , text: I18n.get( "searches.required" ) , attrs: { for: id + "-required" } } ) ] } ) ] } ),
      Dom.el( "div" , { class: "col-auto ms-auto" , children: [ remove ] } ),
      Dom.el( "div" , { class: "col-12 small text-body-secondary group-tally" , text: count } ),
    ] } );
    let body;
    if ( group.mode === "at_least" ) {
      const n = Dom.el( "input" , { class: "form-control form-control-sm" , attrs: { type: "number" , min: "1" , value: String( group.n || 1 ) , id: id + "-n" } } );
      n.addEventListener( "change" , () => { group.n = parseInt( n.value , 10 ) || 1; this.changed(); } );
      const others = this.groups.filter( ( other ) => other !== group );
      const picks = others.map( ( other , j ) => {
        const box = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: id + "-of-" + j } } );
        box.checked = ( group.of || [] ).includes( other.name );
        box.addEventListener( "change" , () => {
          group.of = others.filter( ( o , k ) => Dom.get( id + "-of-" + k ).checked ).map( ( o ) => o.name );
          this.changed();
        } );
        return Dom.el( "div" , { class: "form-check form-check-inline" , children: [ box , Dom.el( "label" , { class: "form-check-label small font-monospace" , text: other.name , attrs: { for: id + "-of-" + j } } ) ] } );
      } );
      body = Dom.el( "div" , { class: "row g-2 align-items-center mt-1" , children: [
        Dom.el( "div" , { class: "col-auto small" , children: [ Dom.el( "label" , { text: I18n.get( "searches.at_least" ) , attrs: { for: id + "-n" } } ) ] } ),
        Dom.el( "div" , { class: "col-3 col-sm-2" , children: [ n ] } ),
        Dom.el( "div" , { class: "col-12 col-sm" , children: picks.length ? picks : [ Dom.el( "span" , { class: "small text-body-secondary" , text: I18n.get( "searches.no_other_groups" ) } ) ] } ),
      ] } );
    } else {
      const terms = Dom.el( "textarea" , { class: "form-control form-control-sm mt-1" , attrs: { rows: "2" , id: id + "-terms" , spellcheck: "false" , placeholder: I18n.get( "searches.terms_placeholder" ) } } );
      terms.value = ( group.terms || [] ).join( "\n" );
      Dom.typed( terms , () => {
        group.terms = terms.value.split( /\n|,/ ).map( ( t ) => t.trim() ).filter( Boolean );
        this.changed();
      } , 500 );
      body = Dom.el( "div" , { children: [ Dom.el( "label" , { class: "visually-hidden" , text: I18n.get( "searches.terms" ) , attrs: { for: id + "-terms" } } ) , terms ] } );
    }
    return Dom.el( "div" , { class: "border rounded p-2" , children: [ head , body ] } );
  },

  tallyOf( name ) {
    if ( !this.answer ) return "";
    const lib = ( this.answer.library_groups || {} )[ name ];
    const miss = ( this.answer.missing_groups || {} )[ name ];
    if ( lib == null && miss == null ) return "";
    return I18n.get( "searches.group_tally" ).replace( "{library}" , ( lib || 0 ).toLocaleString() ).replace( "{missing}" , ( miss || 0 ).toLocaleString() );
  },

  draft() {
    return {
      name: Dom.get( "search-name" ).value.trim(),
      description: Dom.get( "search-description" ).value.trim(),
      query: Dom.get( "search-query" ).value.trim(),
      groups: this.groups,
    };
  },

  changed() {
    this.dirty = true;
    this.paintState();
    this.run();
  },

  // -- running ---------------------------------------------------------------------------

  async run() {
    const ticket = ++this.ticket;
    const draft = this.draft();
    if ( !draft.query && !draft.groups.length ) {
      this.answer = null;
      this.problems( null );
      this.draw();
      return;
    }
    let answer;
    try {
      answer = await Api.post( "/api/searches/try" , Object.assign( {} , draft , { name: draft.name || "Unsaved" , pool: "both" , limit: 2000 } ) );
    } catch ( error ) {
      if ( ticket !== this.ticket ) return;
      this.problems( error );
      return;
    }
    if ( ticket !== this.ticket ) return;
    this.problems( null );
    this.answer = answer;
    // The per-group counts sit in each group's header.
    this.groups.forEach( ( group , index ) => {
      const card = Dom.get( "search-groups" ).children[ index ];
      const cell = card && card.querySelector( ".group-tally" );
      if ( cell ) Dom.text( cell , this.tallyOf( group.name ) );
    } );
    this.draw();
  },

  problems( error ) {
    const box = Dom.get( "search-problems" );
    if ( !error ) {
      Dom.show( box , false );
      return;
    }
    const list = ( error.payload && error.payload.problems ) || [];
    Dom.clear( box );
    if ( list.length ) {
      box.appendChild( Dom.el( "ul" , { class: "mb-0 small" , children: list.map( ( p ) => Dom.el( "li" , { text: p.where + ": " + p.message } ) ) } ) );
    } else Dom.text( box , error.message );
    Dom.show( box , true );
  },

  draw() {
    const answer = this.answer || { library: [] , missing: [] , library_total: 0 , missing_total: 0 };
    Dom.all( "[data-search-pool]" ).forEach( ( tab ) => {
      const name = tab.getAttribute( "data-search-pool" );
      tab.classList.toggle( "active" , name === this.pool );
      if ( name === this.pool ) tab.setAttribute( "aria-current" , "page" );
      else tab.removeAttribute( "aria-current" );
      Dom.text( tab.querySelector( ".badge" ) , ( answer[ name + "_total" ] || 0 ).toLocaleString() );
    } );
    const rows = ( this.pool === "library" ? answer.library : answer.missing ).map( ( row , index ) => Object.assign( { rank: index + 1 } , row ) );
    this.table.redraw();
    this.table.rows( rows );
    const total = answer[ this.pool + "_total" ] || 0;
    Dom.text( Dom.get( "search-tally" ) , total > rows.length ? I18n.get( "table.showing" ).replace( "{shown}" , rows.length.toLocaleString() ).replace( "{total}" , total.toLocaleString() ) : "" );
    Dom.get( "search-add-all" ).disabled = rows.length === 0;
  },

  columns() {
    const library = () => this.pool === "library";
    return [
      { id: "rank" , label: "table.col_rank" , sort: true , firstDesc: false , align: "end" , width: 4 , cellClass: "text-body-secondary" },
      { id: "conn" , label: "missing.col_conn" , sort: true , align: "end" , width: 7 , when: () => !library() , cell: ( row ) => String( row.conn || 0 ) },
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , flex: true , lock: true , width: 22 , cell: ( row ) => (
        library()
          ? Dom.el( "a" , { class: "paper-title" , text: row.title || row.key , attrs: { href: "#paper/" + encodeURIComponent( row.key ) } } )
          : Dom.el( "span" , { class: "paper-title" , text: row.title || row.wid } )
      ) },
      { id: "authors" , label: "table.col_authors" , width: 12 , cellClass: "small" , cell: ( row ) => PaperLinks.authors( row.authors ) },
      { id: "journal" , label: "table.col_journal" , width: 10 , cellClass: "small text-body-secondary" , cell: ( row ) => row.journal || "" },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( row ) => row.year || "" },
      { id: "links" , label: "table.col_links" , width: 9 , cell: ( row ) => ( library() ? PaperLinks.strip( row ) : Missing.links( row ) ) },
      { id: "actions" , label: "table.col_actions" , align: "end" , width: 5 , when: () => !library() , cell: ( row ) => Dom.el( "button" , {
        class: "btn btn-outline-primary btn-sm",
        attrs: { type: "button" , title: I18n.get( "missing.add_title" ) , "aria-label": I18n.get( "missing.add_title" ) },
        children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) ],
        on: { click: () => Missing.addToList( row ) },
      } ) },
    ];
  },

  // "Add all to list…": every row of the tab shown, onto one list.
  addAll() {
    const answer = this.answer;
    if ( !answer ) return null;
    const papers = this.pool === "library"
      ? answer.library.map( ( row ) => row.key )
      : answer.missing.map( ( work ) => Missing.paperOf( work ) );
    const label = I18n.get( "searches.add_all_what" ).replace( "{n}" , papers.length.toLocaleString() ).replace( "{name}" , () => Dom.get( "search-name" ).value.trim() || I18n.get( "searches.unsaved" ) );
    return Missing.addManyToList( papers , label );
  },

  // -- saving ------------------------------------------------------------------------------

  async save() {
    const draft = this.draft();
    const before = this.current;
    let answer;
    try {
      answer = before
        ? await Api.post( "/api/searches/" + encodeURIComponent( before.id ) , draft )
        : await Api.post( "/api/searches" , draft );
    } catch ( error ) {
      this.problems( error );
      return;
    }
    this.current = answer.search;
    this.dirty = false;
    const index = this.list.findIndex( ( s ) => s.id === answer.search.id );
    if ( index >= 0 ) this.list[ index ] = answer.search;
    else this.list.push( answer.search );
    this.list.sort( ( a , b ) => a.name.toLowerCase().localeCompare( b.name.toLowerCase() ) );
    Dom.show( Dom.get( "search-delete" ) , true );
    this.drawList();
    this.paintState();
    Dom.toast( I18n.get( "searches.saved" ) , "success" );
    if ( typeof CrawlView !== "undefined" ) CrawlView.searchesChanged();
  },

  async remove() {
    const search = this.current;
    if ( !search ) return;
    if ( !await Dom.confirm( I18n.get( "searches.delete_confirm" ).replace( "{name}" , () => search.name ) ) ) return;
    let gone = null;
    try {
      await Undo.run( {
        label: I18n.get( "searches.undo_delete" ),
        do: async () => {
          gone = ( await Api.post( "/api/searches/" + encodeURIComponent( search.id ) + "/delete" , {} ) ).search;
          this.list = this.list.filter( ( s ) => s.id !== search.id );
          this.open( this.list[ 0 ] || null );
          if ( typeof CrawlView !== "undefined" ) CrawlView.searchesChanged();
        },
        undo: async () => {
          const back = ( await Api.post( "/api/searches/restore" , { search: gone } ) ).search;
          this.list.push( back );
          this.list.sort( ( a , b ) => a.name.toLowerCase().localeCompare( b.name.toLowerCase() ) );
          this.open( back );
          if ( typeof CrawlView !== "undefined" ) CrawlView.searchesChanged();
        },
      } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },
};
