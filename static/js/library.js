// The Library screen: every paper in Zotero, searched as you type.
//
// There is nothing to import or rebuild. The server reads Zotero live and
// says so over /api/library/stream: "changed" when papers were added, changed
// or removed (the list is fetched again, keeping the search), "progress"
// while full text is being made searchable (the status line moves on).
const Library = {
  pageSize: 50,
  query: "",
  offset: 0,
  // Bumped by every fetch, so an answer that arrives after a newer one is
  // dropped instead of overwriting it.
  ticket: 0,
  timer: null,
  stream: null,

  async init() {
    Dom.show( Dom.get( "library-panel" ) , true );
    ViewHead.watch( Dom.get( "library-panel" ) );
    await PaperLinks.init();
    const search = Dom.get( "library-search" );
    search.addEventListener( "input" , () => this.later() );
    Dom.get( "library-title-mode" ).addEventListener( "change" , () => this.refresh() );
    Dom.onPress( Dom.get( "library-more" ) , () => this.more() );
    Dom.all( "[data-library-has]" ).forEach( ( box ) => box.addEventListener( "change" , () => this.refresh() ) );
    this.table = new DataTable( {
      name: "library",
      holder: Dom.get( "library-table" ),
      menu: Dom.get( "library-columns" ),
      columns: this.columns(),
      sort: [ { col: "added" , desc: true } ],
      onSort: () => this.refresh(),
      onEnd: () => ( Dom.get( "library-more" ).hidden ? null : this.more() ),
    } );
    this.paintFilter = DataTable.filters( Dom.get( "library-filter" ) ,
      () => Dom.all( "[data-library-has]" ).filter( ( box ) => box.checked ).length + ( Dom.get( "library-title-mode" ).checked ? 1 : 0 ),
      () => {
        Dom.all( "[data-library-has]" ).forEach( ( box ) => { box.checked = false; } );
        Dom.get( "library-title-mode" ).checked = false;
        this.refresh();
      } );
    this.listen();
    await this.refresh();
  },

  later() {
    clearTimeout( this.timer );
    this.timer = setTimeout( () => this.refresh() , 200 );
  },

  searching() {
    return Dom.get( "library-search" ).value.trim() !== "";
  },

  // The table's columns. Best match only while searching; the server sorts.
  columns() {
    return [
      { id: "relevance" , label: "table.col_match" , sort: true , align: "end" , width: 5 , when: () => this.searching() ,
        cell: ( paper ) => ( paper.score == null ? "" : String( Math.round( paper.score ) ) ) },
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , flex: true , lock: true , width: 20 , cell: ( paper ) => Content.titleLink( paper ) },
      { id: "authors" , label: "table.col_authors" , sort: true , firstDesc: false , width: 12 , cellClass: "small" , cell: ( paper ) => PaperLinks.authors( paper.authors ) },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( paper ) => paper.year || "" },
      { id: "journal" , label: "table.col_journal" , sort: true , firstDesc: false , width: 11 , cellClass: "small text-body-secondary" , cell: ( paper ) => paper.journal || "" },
      { id: "added" , label: "table.col_added" , sort: true , width: 7 , cellClass: "small text-nowrap" , cell: ( paper ) => Dom.when( paper.added || "" , "" ) },
      { id: "links" , label: "table.col_links" , width: 8 , cell: ( paper ) => PaperLinks.strip( paper ) },
      { id: "text" , label: "table.col_text" , width: 6 , cell: ( paper ) => this.textBadge( paper ) },
      { id: "content" , label: "table.col_content" , width: 12 , cell: ( paper ) => Content.strip( paper.key , paper.content ) },
      { id: "tags" , label: "table.col_tags" , width: 12 , hide: true , cellClass: "small text-body-secondary" , cell: ( paper ) => ( paper.tags || [] ).join( ", " ) },
    ];
  },

  params( offset ) {
    const params = new URLSearchParams();
    const text = Dom.get( "library-search" ).value.trim();
    if ( text ) params.set( "q" , text );
    if ( Dom.get( "library-title-mode" ).checked ) params.set( "mode" , "title" );
    // A search starts in best-match order; a header click picks another.
    const first = this.table.activeSort()[ 0 ] || { col: this.searching() ? "relevance" : "added" , desc: true };
    params.set( "sort" , first.col );
    params.set( "dir" , first.desc ? "desc" : "asc" );
    const has = Dom.all( "[data-library-has]" ).filter( ( box ) => box.checked ).map( ( box ) => box.getAttribute( "data-library-has" ) );
    if ( has.length ) params.set( "has" , has.join( "," ) );
    params.set( "limit" , String( this.pageSize ) );
    params.set( "offset" , String( offset ) );
    return params;
  },

  async refresh() {
    // Starting or clearing a search: best match first, or newest first.
    if ( this.hadSearch !== this.searching() ) {
      this.hadSearch = this.searching();
      this.table.setSort( [ { col: this.hadSearch ? "relevance" : "added" , desc: true } ] );
      this.table.redraw();
    }
    this.paintFilter();
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/papers?" + this.params( 0 ) );
    if ( ticket !== this.ticket ) return;
    this.offset = 0;
    this.show( answer , false );
  },

  async more() {
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/papers?" + this.params( this.offset ) );
    if ( ticket !== this.ticket ) return;
    this.show( answer , true );
  },

  show( answer , appending ) {
    this.table.rows( answer.papers , appending );
    this.offset = answer.next == null ? this.offset + answer.papers.length : answer.next;
    Dom.show( Dom.get( "library-more" ) , answer.next != null );
    Dom.show( Dom.get( "library-fuzzy" ) , Boolean( answer.fuzzy ) );
    Dom.show( Dom.get( "library-empty" ) , !appending && answer.total === 0 && answer.status.ready );
    Dom.text( Dom.get( "library-results-count" ) , I18n.get( "table.showing" ).replace( "{shown}" , this.offset.toLocaleString() ).replace( "{total}" , answer.total.toLocaleString() ) );
    this.status( answer.status );
  },

  status( status ) {
    Dom.text( Dom.get( "library-count" ) , I18n.get( "library.count" ).replace( "{count}" , ( status.papers || 0 ).toLocaleString() ) );
    let text;
    if ( status.error ) text = I18n.get( "library.zotero_missing" ).replace( "{error}" , () => status.error );
    else if ( !status.ready ) text = I18n.get( "library.loading" );
    else if ( status.text_pending > 0 ) text = I18n.get( "library.indexing" ).replace( "{pending}" , status.text_pending.toLocaleString() );
    else {
      text = I18n.get( "library.ready" )
        .replace( "{with_text}" , ( status.with_text || 0 ).toLocaleString() )
        .replace( "{papers}" , ( status.papers || 0 ).toLocaleString() );
    }
    Dom.text( Dom.get( "library-status" ) , text );
  },

  textBadge( paper ) {
    if ( !paper.has_pdf ) return Dom.el( "span" , { class: "badge text-bg-light border" , text: I18n.get( "library.no_pdf" ) } );
    if ( !paper.has_text ) {
      return Dom.el( "span" , {
        class: "badge bg-warning-subtle text-warning-emphasis border",
        text: I18n.get( "library.no_text" ),
        attrs: { title: I18n.get( "library.no_text_title" ) },
      } );
    }
    return null;
  },

  // Live: the server says when the library moved.
  listen() {
    if ( this.stream ) return;
    this.stream = true;
    Content.on( "changed" , () => {
      // Not while someone is mid-scroll through a long list: fetching again
      // would throw away the pages they loaded. The status line still moves.
      if ( this.offset <= this.pageSize ) this.refresh();
      else this.refreshStatus();
    } );
    Content.on( "progress" , () => this.refreshStatus() );
  },

  async refreshStatus() {
    try {
      this.status( await Api.request( "/api/library/status" ) );
    } catch ( error ) { /* the next event tries again */ }
  },
};
