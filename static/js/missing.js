// The Missing screen: the papers you do not have yet. The works your library
// cites (in bibliographies) and the works citing it (newer / citing), with how
// many of your papers connect to each, so the ones worth getting rise to the
// top. It fills in as each paper's OpenAlex stage lands; nothing to rebuild.
//
// #missing/<key> narrows it to one library paper's network (the Paper
// screen's link). Sorting is tiered: clicking a column makes it the primary
// order and the earlier ones break its ties, shown as small rank numbers.
const Missing = {
  tab: "all",
  sort: [ { col: "conn" , desc: true } , { col: "cited_by" , desc: true } ],
  pageSize: 100,
  offset: 0,
  ticket: 0,
  paper: "",
  lists: null,
  dirty: false,
  timer: null,

  init() {
    Dom.show( Dom.get( "missing-panel" ) , true );
    Dom.all( "[data-missing-tab]" ).forEach( ( tab ) => {
      tab.addEventListener( "click" , ( event ) => {
        event.preventDefault();
        this.tab = tab.getAttribute( "data-missing-tab" );
        this.refresh();
      } );
    } );
    Dom.typed( Dom.get( "missing-search" ) , () => this.refresh() , 250 );
    Dom.get( "missing-show-skipped" ).addEventListener( "change" , () => this.refresh() );
    Dom.onPress( Dom.get( "missing-more" ) , () => this.more() );
    Dom.get( "missing-add-form" ).addEventListener( "submit" , ( event ) => {
      event.preventDefault();
      this.confirmAdd().catch( ( error ) => Dom.toast( error.message , "error" ) );
    } );
    Dom.onPress( Dom.get( "missing-clear-paper" ) , () => { window.location.hash = "#missing"; } );
    this.works = new DataTable( {
      name: "missing",
      holder: Dom.get( "missing-works" ),
      menu: Dom.get( "missing-columns" ),
      columns: this.workColumns(),
      sort: this.sort,
      tiers: 3,
      onSort: ( sort ) => { this.sort = sort; this.refresh(); },
      onEnd: () => this.moreIfAny(),
      rowClass: ( work ) => ( work.skipped ? "table-secondary" : "" ),
    } );
    this.people = new DataTable( {
      name: "missing-authors",
      holder: Dom.get( "missing-authors" ),
      menu: null,
      columns: this.authorColumns(),
      sort: [ { col: "rank" , desc: false } ],
    } );
    this.paintFilter = DataTable.filters( Dom.get( "missing-filter" ) ,
      () => ( Dom.get( "missing-show-skipped" ).checked ? 1 : 0 ),
      () => { Dom.get( "missing-show-skipped" ).checked = false; this.refresh(); } );
    window.addEventListener( "hashchange" , () => this.route() );
    // The pool grows as OpenAlex results land; refetch when the screen is
    // looked at, and live while it is (not mid-scroll, which would lose pages).
    const refresh = Content.throttle( () => {
      if ( Nav.current() === "missing" && this.offset <= this.pageSize ) this.refresh();
    } , 20000 );
    Content.on( "paper" , ( data ) => {
      if ( data.stage !== "openalex" ) return;
      this.dirty = true;
      refresh();
    } );
    this.route( true );
  },

  route( first ) {
    const hash = window.location.hash.replace( /^#/ , "" );
    if ( hash.split( "/" )[ 0 ] !== "missing" ) return;
    let paper = "";
    if ( hash.startsWith( "missing/" ) ) {
      try {
        paper = decodeURIComponent( hash.slice( "missing/".length ) );
      } catch ( error ) {
        paper = "";
      }
    }
    if ( first || paper !== this.paper || this.dirty || !this.loaded ) {
      this.paper = paper;
      this.refresh();
    }
  },

  searching() {
    return Dom.get( "missing-search" ).value.trim() !== "";
  },

  sortParam() {
    return this.works.activeSort().map( ( entry ) => entry.col + ":" + ( entry.desc ? "desc" : "asc" ) ).join( "," );
  },

  // The columns of the works table. The match score only while searching.
  workColumns() {
    return [
      { id: "relevance" , label: "table.col_match" , sort: true , align: "end" , width: 5 , when: () => this.searching() ,
        cell: ( work ) => ( work.score == null ? "" : String( Math.round( work.score ) ) ) },
      { id: "conn" , label: "missing.col_conn" , title: "missing.col_conn_title" , sort: true , align: "end" , width: 8 , cell: ( work ) => {
        const span = Dom.el( "span" , { class: "fw-semibold" , text: String( work.conn ) } );
        span.setAttribute( "title" , I18n.get( "missing.conn_title" ).replace( "{refs}" , work.lib_cites ).replace( "{citing}" , work.cites_lib ) );
        return span;
      } },
      { id: "cited_by" , label: "missing.col_cited" , title: "missing.col_cited_title" , sort: true , align: "end" , width: 7 ,
        cell: ( work ) => ( work.cited_by || 0 ).toLocaleString() },
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , flex: true , lock: true , width: 20 ,
        cell: ( work ) => Dom.el( "span" , { class: "paper-title" , text: work.title || work.wid } ) },
      { id: "authors" , label: "table.col_authors" , width: 12 , cellClass: "small" , cell: ( work ) => PaperLinks.authors( work.authors ) },
      { id: "journal" , label: "table.col_journal" , width: 10 , cellClass: "small text-body-secondary" , cell: ( work ) => work.journal || "" },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( work ) => work.year || "" },
      { id: "links" , label: "table.col_links" , width: 9 , cell: ( work ) => this.links( work ) },
      { id: "actions" , label: "table.col_actions" , align: "end" , width: 7 , cell: ( work ) => this.actions( work ) },
    ];
  },

  authorColumns() {
    return [
      { id: "rank" , label: "table.col_rank" , sort: true , firstDesc: false , align: "end" , width: 4 , cellClass: "text-body-secondary" },
      { id: "name" , label: "table.col_name" , sort: true , firstDesc: false , flex: true , lock: true , width: 16 , cellClass: "fw-semibold" ,
        value: ( author ) => author.name || author.openalex , cell: ( author ) => author.name || author.openalex },
      { id: "links" , label: "table.col_links" , width: 10 , cell: ( author ) => {
        const links = [ PaperLinks.link( "https://openalex.org/" + author.openalex , "missing.openalex" , "missing.openalex_title" ) ];
        if ( author.orcid ) links.unshift( PaperLinks.link( "https://orcid.org/" + author.orcid , "missing.orcid" , "missing.orcid_title" ) );
        return Dom.el( "span" , { class: "paper-links" , children: links } );
      } },
      { id: "papers" , label: "missing.author_papers" , sort: true , align: "end" , width: 7 },
      { id: "lib_cites" , label: "missing.col_conn" , sort: true , align: "end" , width: 8 },
    ];
  },

  params( offset ) {
    const params = new URLSearchParams();
    const text = Dom.get( "missing-search" ).value.trim();
    if ( text ) params.set( "q" , text );
    params.set( "pool" , this.tab === "authors" ? "all" : this.tab );
    params.set( "sort" , this.sortParam() );
    if ( Dom.get( "missing-show-skipped" ).checked ) params.set( "skipped" , "show" );
    if ( this.paper ) params.set( "paper" , this.paper );
    params.set( "limit" , String( this.pageSize ) );
    params.set( "offset" , String( offset ) );
    return params;
  },

  async refresh() {
    this.dirty = false;
    this.loaded = true;
    const ticket = ++this.ticket;
    const authors = this.tab === "authors";
    let answer;
    let people = null;
    try {
      [ answer , people ] = await Promise.all( [
        Api.request( "/api/missing?" + this.params( 0 ) ),
        authors ? Api.request( "/api/missing/authors" ) : Promise.resolve( null ),
      ] );
    } catch ( error ) {
      if ( ticket === this.ticket ) Dom.toast( error.message , "error" );
      return;
    }
    if ( ticket !== this.ticket ) return;
    this.counts( answer , people );
    this.paperLine( answer.paper );
    Dom.show( Dom.get( "missing-works" ) , !authors );
    Dom.show( Dom.get( "missing-authors" ) , authors );
    this.paintFilter();
    if ( authors ) {
      this.people.options.menu = Dom.get( "missing-columns" );
      this.people.drawMenu();
      this.people.rows( people.authors.map( ( author , index ) => Object.assign( { rank: index + 1 } , author ) ) );
      Dom.show( Dom.get( "missing-more" ) , false );
      Dom.show( Dom.get( "missing-empty" ) , people.authors.length === 0 );
      Dom.text( Dom.get( "missing-total" ) , I18n.get( "table.showing" ).replace( "{shown}" , people.authors.length.toLocaleString() ).replace( "{total}" , people.authors.length.toLocaleString() ) );
      return;
    }
    this.works.drawMenu();
    this.offset = 0;
    this.show( answer , false );
  },

  async more() {
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/missing?" + this.params( this.offset ) );
    if ( ticket !== this.ticket ) return;
    this.show( answer , true );
  },

  // Scrolled near the bottom of the table: the next page, if there is one.
  moreIfAny() {
    if ( this.tab === "authors" || Dom.get( "missing-more" ).hidden ) return null;
    return this.more();
  },

  show( answer , appending ) {
    // The match column comes and goes with the search.
    if ( !appending && this.hadSearch !== this.searching() ) {
      this.hadSearch = this.searching();
      this.works.redraw();
    }
    this.works.paintSort();
    this.works.rows( answer.works , appending );
    this.offset = answer.next == null ? this.offset + answer.works.length : answer.next;
    Dom.show( Dom.get( "missing-more" ) , answer.next != null );
    Dom.show( Dom.get( "missing-empty" ) , answer.total === 0 );
    Dom.text( Dom.get( "missing-total" ) , I18n.get( "table.showing" ).replace( "{shown}" , this.offset.toLocaleString() ).replace( "{total}" , answer.total.toLocaleString() ) );
  },

  counts( answer , people ) {
    const counts = answer.counts || {};
    Dom.all( "[data-missing-tab]" ).forEach( ( tab ) => {
      const name = tab.getAttribute( "data-missing-tab" );
      tab.classList.toggle( "active" , name === this.tab );
      if ( name === this.tab ) tab.setAttribute( "aria-current" , "page" );
      else tab.removeAttribute( "aria-current" );
      const badge = tab.querySelector( ".badge" );
      if ( !badge ) return;
      const n = name === "authors" ? ( people ? people.authors.length : null ) : counts[ name ];
      Dom.text( badge , n == null ? "" : n.toLocaleString() );
      Dom.show( badge , n != null );
    } );
    const skipped = Dom.get( "missing-skipped-count" );
    Dom.text( skipped , answer.skipped ? I18n.get( "missing.skipped_count" ).replace( "{n}" , answer.skipped ) : "" );
  },

  paperLine( paper ) {
    Dom.show( Dom.get( "missing-paper" ) , Boolean( paper ) );
    if ( !paper ) return;
    const link = Dom.get( "missing-paper-link" );
    Dom.text( link , paper.title || paper.key );
    link.setAttribute( "href" , "#paper/" + encodeURIComponent( paper.key ) );
  },

  links( work ) {
    const links = [];
    if ( work.doi ) {
      links.push( PaperLinks.link( "https://doi.org/" + work.doi , "links.doi" , "links.doi_title" ) );
      if ( PaperLinks.proxyUrl ) links.push( PaperLinks.link( PaperLinks.proxyUrl.replace( "{doi}" , () => work.doi ) , "links.proxy" , "links.proxy_title" ) );
    }
    if ( work.oa_pdf ) links.push( PaperLinks.link( work.oa_pdf , "missing.oa_pdf" , "missing.oa_pdf_title" ) );
    links.push( PaperLinks.link( "https://openalex.org/" + work.wid , "missing.openalex" , "missing.openalex_title" ) );
    return Dom.el( "span" , { class: "paper-links" , children: links } );
  },

  actions( work ) {
    const skip = Dom.el( "button" , {
      class: "btn btn-outline-secondary btn-sm",
      text: I18n.get( work.skipped ? "missing.unskip" : "missing.skip" ),
      on: { click: () => this.skip( work , !work.skipped , skip.closest( "tr" ) ) },
    } );
    const add = Dom.el( "button" , {
      class: "btn btn-outline-primary btn-sm",
      attrs: { title: I18n.get( "missing.add_title" ) },
      children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { class: "visually-hidden" , text: I18n.get( "missing.add_title" ) } ) ],
      on: { click: () => this.addToList( work ) },
    } );
    return Dom.el( "div" , { class: "d-inline-flex gap-1" , children: [ add , skip ] } );
  },

  async skip( work , skip , tr ) {
    const send = ( value ) => Api.post( "/api/missing/skip" , { wids: [ work.wid ] , skip: value } );
    await send( skip );
    const showing = Dom.get( "missing-show-skipped" ).checked;
    if ( skip && !showing ) tr.remove();
    else this.refresh();
    Dom.toast( I18n.get( skip ? "missing.skipped_toast" : "missing.unskipped_toast" ) , "success" , skip ? {
      text: I18n.get( "missing.unskip" ),
      run: async () => { await send( false ); this.refresh(); },
    } : null );
  },

  // "Add to list…": the work goes onto a list as a paper object, with its
  // OpenAlex id, DOI and open-access PDF.
  async addToList( work ) {
    if ( !this.lists ) {
      const answer = await Api.request( "/api/lists?limit=200" );
      this.lists = answer.lists;
    }
    const picker = Dom.get( "missing-add-list" );
    Dom.clear( picker );
    this.lists.forEach( ( list ) => picker.appendChild( Dom.el( "option" , { text: list.name , attrs: { value: list.slug } } ) ) );
    if ( Lists.slug ) picker.value = Lists.slug;
    Dom.text( Dom.get( "missing-add-title" ) , work.title || work.wid );
    this.adding = work;
    bootstrap.Modal.getOrCreateInstance( Dom.get( "missing-add-dialog" ) ).show();
  },

  async confirmAdd() {
    const work = this.adding;
    const slug = Dom.get( "missing-add-list" ).value;
    if ( !work || !slug ) return;
    const paper = { title: work.title , doi: work.doi , year: work.year , journal: work.journal , authors: ( work.authors || [] ).join( ", " ) , wid: work.wid , pdf: work.oa_pdf || "" };
    await Api.post( "/api/lists/" + encodeURIComponent( slug ) + "/ops" , { ops: [ { op: "add" , paper: paper , if_absent: true } ] } );
    bootstrap.Modal.getOrCreateInstance( Dom.get( "missing-add-dialog" ) ).hide();
    const name = ( this.lists.find( ( list ) => list.slug === slug ) || {} ).name || slug;
    Dom.toast( I18n.get( "missing.added" ).replace( "{list}" , () => name ) , "success" );
  },
};
