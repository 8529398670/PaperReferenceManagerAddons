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
    Dom.all( "[data-missing-sort]" ).forEach( ( head ) => {
      head.addEventListener( "click" , () => this.sortBy( head.getAttribute( "data-missing-sort" ) ) );
    } );
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

  sortBy( col ) {
    const first = this.sort[ 0 ];
    if ( first && first.col === col ) {
      first.desc = !first.desc;
    } else {
      const rest = this.sort.filter( ( entry ) => entry.col !== col );
      this.sort = [ { col: col , desc: col !== "title" } , ...rest ].slice( 0 , 3 );
    }
    this.refresh();
  },

  sortParam() {
    const searching = Dom.get( "missing-search" ).value.trim() !== "";
    return this.sort.filter( ( entry ) => searching || entry.col !== "relevance" ).map( ( entry ) => entry.col + ":" + ( entry.desc ? "desc" : "asc" ) ).join( "," );
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
    if ( authors ) {
      this.drawAuthors( people.authors );
      Dom.show( Dom.get( "missing-more" ) , false );
      Dom.show( Dom.get( "missing-empty" ) , people.authors.length === 0 );
      return;
    }
    Dom.clear( Dom.get( "missing-rows" ) );
    this.offset = 0;
    this.show( answer );
  },

  async more() {
    const ticket = ++this.ticket;
    const answer = await Api.request( "/api/missing?" + this.params( this.offset ) );
    if ( ticket !== this.ticket ) return;
    this.show( answer );
  },

  show( answer ) {
    const searching = Dom.get( "missing-search" ).value.trim() !== "";
    Dom.show( Dom.get( "missing-col-relevance" ) , searching );
    this.paintSort( searching );
    const body = Dom.get( "missing-rows" );
    answer.works.forEach( ( work ) => body.appendChild( this.row( work , searching ) ) );
    Content.label( body.closest( "table" ) );
    this.offset = answer.next == null ? this.offset + answer.works.length : answer.next;
    Dom.show( Dom.get( "missing-more" ) , answer.next != null );
    Dom.show( Dom.get( "missing-empty" ) , answer.total === 0 );
    Dom.text( Dom.get( "missing-total" ) , I18n.get( "missing.showing" ).replace( "{shown}" , this.offset.toLocaleString() ).replace( "{total}" , answer.total.toLocaleString() ) );
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

  paintSort( searching ) {
    const ranks = {};
    this.sort.filter( ( entry ) => searching || entry.col !== "relevance" ).forEach( ( entry , index ) => { ranks[ entry.col ] = { rank: index + 1 , desc: entry.desc }; } );
    Dom.all( "[data-missing-sort]" ).forEach( ( head ) => {
      const col = head.getAttribute( "data-missing-sort" );
      const th = head.closest( "th" );
      const mark = head.querySelector( ".sort-mark" );
      const found = ranks[ col ];
      th.setAttribute( "aria-sort" , found && found.rank === 1 ? ( found.desc ? "descending" : "ascending" ) : "none" );
      Dom.clear( mark );
      // The primary column's arrow is style.css's (aria-sort); a tie-breaker
      // carries its rank and its own arrow.
      if ( found && found.rank > 1 ) mark.appendChild( Dom.el( "i" , { class: "bi bi-arrow-" + ( found.desc ? "down" : "up" ) + " small" , attrs: { "aria-hidden": "true" } } ) );
      if ( found ) mark.appendChild( Dom.el( "sup" , { text: String( found.rank ) } ) );
    } );
  },

  row( work , searching ) {
    const cells = [];
    if ( searching ) cells.push( Dom.el( "td" , { class: "text-end text-nowrap" , text: work.score == null ? "" : String( Math.round( work.score ) ) } ) );
    const conn = Dom.el( "td" , { class: "text-end text-nowrap" , children: [ Dom.el( "span" , { class: "fw-semibold" , text: String( work.conn ) } ) ] } );
    conn.setAttribute( "title" , I18n.get( "missing.conn_title" ).replace( "{refs}" , work.lib_cites ).replace( "{citing}" , work.cites_lib ) );
    cells.push( conn );
    cells.push( Dom.el( "td" , { class: "text-end text-nowrap" , text: ( work.cited_by || 0 ).toLocaleString() } ) );
    const meta = [ PaperLinks.authors( work.authors ) , work.journal ].filter( Boolean ).join( " · " );
    cells.push( Dom.el( "td" , { class: "missing-title" , children: [
      Dom.el( "div" , { class: "paper-title" , text: work.title || work.wid } ),
      Dom.el( "div" , { class: "paper-meta" , text: meta } ),
    ] } ) );
    cells.push( Dom.el( "td" , { class: "text-nowrap" , text: work.year || "" } ) );
    const links = [];
    if ( work.doi ) {
      links.push( PaperLinks.link( "https://doi.org/" + work.doi , "links.doi" , "links.doi_title" ) );
      if ( PaperLinks.proxyUrl ) links.push( PaperLinks.link( PaperLinks.proxyUrl.replace( "{doi}" , () => work.doi ) , "links.proxy" , "links.proxy_title" ) );
    }
    if ( work.oa_pdf ) links.push( PaperLinks.link( work.oa_pdf , "missing.oa_pdf" , "missing.oa_pdf_title" ) );
    links.push( PaperLinks.link( "https://openalex.org/" + work.wid , "missing.openalex" , "missing.openalex_title" ) );
    cells.push( Dom.el( "td" , { class: "missing-links" , children: [ Dom.el( "span" , { class: "paper-links" , children: links } ) ] } ) );
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
    cells.push( Dom.el( "td" , { class: "text-end text-nowrap" , children: [ Dom.el( "div" , { class: "d-inline-flex gap-1" , children: [ add , skip ] } ) ] } ) );
    const tr = Dom.el( "tr" , { children: cells } );
    if ( work.skipped ) tr.classList.add( "table-secondary" );
    return tr;
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

  drawAuthors( authors ) {
    const body = Dom.get( "missing-author-rows" );
    Dom.clear( body );
    authors.forEach( ( author , index ) => {
      const links = [ PaperLinks.link( "https://openalex.org/" + author.openalex , "missing.openalex" , "missing.openalex_title" ) ];
      if ( author.orcid ) links.unshift( PaperLinks.link( "https://orcid.org/" + author.orcid , "missing.orcid" , "missing.orcid_title" ) );
      body.appendChild( Dom.el( "tr" , { children: [
        Dom.el( "td" , { class: "text-end text-body-secondary" , text: String( index + 1 ) } ),
        Dom.el( "td" , { class: "fw-semibold" , text: author.name || author.openalex } ),
        Dom.el( "td" , { children: [ Dom.el( "span" , { class: "paper-links" , children: links } ) ] } ),
        Dom.el( "td" , { class: "text-end" , text: String( author.papers ) } ),
        Dom.el( "td" , { class: "text-end" , text: String( author.lib_cites ) } ),
      ] } ) );
    } );
    Content.label( body.closest( "table" ) );
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
