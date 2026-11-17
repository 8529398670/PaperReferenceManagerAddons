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
    await PaperLinks.init();
    const search = Dom.get( "library-search" );
    search.addEventListener( "input" , () => this.later() );
    Dom.get( "library-sort" ).addEventListener( "change" , () => this.refresh() );
    Dom.get( "library-title-mode" ).addEventListener( "change" , () => this.refresh() );
    Dom.onPress( Dom.get( "library-more" ) , () => this.more() );
    Dom.all( "[data-library-has]" ).forEach( ( box ) => box.addEventListener( "change" , () => this.refresh() ) );
    this.listen();
    await this.refresh();
  },

  later() {
    clearTimeout( this.timer );
    this.timer = setTimeout( () => this.refresh() , 200 );
  },

  params( offset ) {
    const params = new URLSearchParams();
    const text = Dom.get( "library-search" ).value.trim();
    if ( text ) params.set( "q" , text );
    if ( Dom.get( "library-title-mode" ).checked ) params.set( "mode" , "title" );
    const sort = Dom.get( "library-sort" ).value;
    params.set( "sort" , sort );
    params.set( "dir" , sort === "title" ? "asc" : "desc" );
    const has = Dom.all( "[data-library-has]" ).filter( ( box ) => box.checked ).map( ( box ) => box.getAttribute( "data-library-has" ) );
    if ( has.length ) params.set( "has" , has.join( "," ) );
    params.set( "limit" , String( this.pageSize ) );
    params.set( "offset" , String( offset ) );
    return params;
  },

  async refresh() {
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/papers?" + this.params( 0 ) );
    if ( ticket !== this.ticket ) return;
    Dom.clear( Dom.get( "library-results" ) );
    this.show( answer , false );
  },

  async more() {
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/papers?" + this.params( this.offset ) );
    if ( ticket !== this.ticket ) return;
    this.show( answer , true );
  },

  show( answer , appending ) {
    const list = Dom.get( "library-results" );
    answer.papers.forEach( ( paper ) => list.appendChild( this.row( paper ) ) );
    this.offset = answer.next == null ? this.offset + answer.papers.length : answer.next;
    Dom.show( Dom.get( "library-more" ) , answer.next != null );
    const searching = Dom.get( "library-search" ).value.trim() !== "";
    Dom.show( Dom.get( "library-fuzzy" ) , Boolean( answer.fuzzy ) );
    Dom.show( Dom.get( "library-empty" ) , !appending && answer.total === 0 && answer.status.ready );
    const filtered = Dom.all( "[data-library-has]" ).some( ( box ) => box.checked );
    const count = Dom.get( "library-results-count" );
    Dom.text( count , I18n.get( "library.results" ).replace( "{total}" , answer.total.toLocaleString() ) );
    Dom.show( count , ( searching || filtered ) && !answer.fuzzy );
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

  row( paper ) {
    const badges = [];
    if ( !paper.has_pdf ) {
      badges.push( Dom.el( "span" , { class: "badge text-bg-light border" , text: I18n.get( "library.no_pdf" ) } ) );
    } else if ( !paper.has_text ) {
      badges.push( Dom.el( "span" , {
        class: "badge bg-warning-subtle text-warning-emphasis border",
        text: I18n.get( "library.no_text" ),
        attrs: { title: I18n.get( "library.no_text_title" ) },
      } ) );
    }
    return Dom.el( "li" , {
      class: "paper-item",
      children: [
        Dom.el( "div" , { children: [ Content.titleLink( paper ) ] } ),
        Dom.el( "div" , { class: "paper-meta" , text: PaperLinks.meta( paper ) } ),
        Dom.el( "div" , { class: "paper-foot" , children: [ PaperLinks.strip( paper ) , ...badges , Content.strip( paper.key , paper.content ) ] } ),
      ],
    } );
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
