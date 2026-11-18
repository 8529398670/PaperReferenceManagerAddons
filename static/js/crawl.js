// The Missing screen's Crawl tab: a best-first walk over OpenAlex from the
// library papers matching a saved search, looking for papers you lack
// (app/extras/crawl.py). One crawl runs at a time, in the background; its
// progress arrives on the library stream ("crawl"), and each saved search
// keeps its last result: the novel works (not in the library, matching
// enough of the search's terms) and every work visited, each with its score,
// how deep it was and the work it was reached from.
const CrawlView = {
  active: false,
  status: {},
  runs: [],
  view: "novel",
  total: null,

  init() {
    this.table = new DataTable( {
      name: "crawl",
      holder: Dom.get( "crawl-table" ),
      menu: null,
      columns: this.columns(),
      sort: [ { col: "score" , desc: true } ],
    } );
    Dom.onSubmit( Dom.get( "crawl-form" ) , ( event ) => {
      event.preventDefault();
      return this.start();
    } );
    Dom.onPress( Dom.get( "crawl-stop" ) , () => this.stop() );
    Dom.get( "crawl-search" ).addEventListener( "change" , () => this.loadResult() );
    Dom.all( "input[name=crawl-view]" ).forEach( ( radio ) => radio.addEventListener( "change" , () => {
      this.view = radio.value;
      this.loadResult();
    } ) );
    Content.on( "crawl" , ( status ) => {
      const finished = this.status.running && !status.running;
      this.status = status;
      this.paintStatus();
      if ( finished && this.active ) this.refresh();
    } );
  },

  // Missing.refresh says whether the tab is showing.
  showing( on ) {
    if ( !this.table ) this.init();
    Dom.show( Dom.get( "crawl-panel" ) , on );
    Dom.show( Dom.get( "crawl-table" ) , on );
    if ( on && !this.active ) this.refresh();
    this.active = on;
  },

  count() {
    return this.total;
  },

  async searchesChanged() {
    if ( this.active ) await this.refresh();
  },

  async refresh() {
    let answer;
    let searches;
    try {
      [ answer , searches ] = await Promise.all( [ Api.request( "/api/crawl" ) , Api.request( "/api/searches" ) ] );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.status = answer.status;
    this.runs = answer.runs;
    const picker = Dom.get( "crawl-search" );
    const before = picker.value || this.status.search_id || ( this.runs[ 0 ] || {} ).search_id || "";
    Dom.clear( picker );
    searches.searches.forEach( ( search ) => picker.appendChild( Dom.el( "option" , { text: search.name , attrs: { value: search.id } } ) ) );
    if ( !searches.searches.length ) picker.appendChild( Dom.el( "option" , { text: I18n.get( "crawl.no_searches" ) , attrs: { value: "" } } ) );
    if ( before && searches.searches.some( ( s ) => s.id === before ) ) picker.value = before;
    Dom.get( "crawl-start" ).disabled = !searches.searches.length;
    this.paintStatus();
    await this.loadResult();
  },

  paintStatus() {
    const status = this.status || {};
    const running = Boolean( status.running );
    Dom.show( Dom.get( "crawl-stop" ) , running );
    Dom.get( "crawl-start" ).disabled = running || !Dom.get( "crawl-search" ).value;
    Dom.show( Dom.get( "crawl-progress" ) , running || Boolean( status.error ) );
    const bar = Dom.get( "crawl-progress-bar" );
    const share = running && status.max_visits ? Math.round( 100 * ( status.visited || 0 ) / status.max_visits ) : 100;
    bar.style.width = share + "%";
    bar.classList.toggle( "bg-danger" , Boolean( status.error ) );
    bar.classList.toggle( "progress-bar-animated" , running );
    let text = "";
    if ( running ) {
      text = I18n.get( "crawl.running" ).replace( "{search}" , () => status.search || "" ).replace( "{visited}" , ( status.visited || 0 ).toLocaleString() )
        .replace( "{max}" , ( status.max_visits || 0 ).toLocaleString() ).replace( "{novel}" , ( status.novel || 0 ).toLocaleString() )
        .replace( "{api}" , ( status.api_used || 0 ).toLocaleString() );
    } else if ( status.error ) {
      text = I18n.get( "crawl.failed" ).replace( "{error}" , () => status.error );
    }
    Dom.text( Dom.get( "crawl-progress-text" ) , text );
  },

  settings() {
    const number = ( id ) => Number( Dom.get( id ).value );
    return {
      search: Dom.get( "crawl-search" ).value,
      max_visits: number( "crawl-max-visits" ),
      max_depth: number( "crawl-max-depth" ),
      api_budget: number( "crawl-api-budget" ),
      min_novel_hits: number( "crawl-min-novel" ),
      min_seed_hits: number( "crawl-min-seed" ),
      keyword_weight: number( "crawl-keyword-weight" ),
      cite_weight: number( "crawl-cite-weight" ),
      link_weight: number( "crawl-link-weight" ),
      cited_by: Dom.get( "crawl-cited-by" ).checked,
    };
  },

  async start() {
    try {
      const answer = await Api.post( "/api/crawl" , this.settings() );
      this.status = answer.status;
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.paintStatus();
    Dom.toast( I18n.get( "crawl.started" ) , "success" );
  },

  async stop() {
    const answer = await Api.post( "/api/crawl/stop" , {} );
    this.status = answer.status;
    this.paintStatus();
  },

  async loadResult() {
    const id = Dom.get( "crawl-search" ).value;
    const run = this.runs.find( ( r ) => r.search_id === id );
    this.paintStatus();
    const exportLink = Dom.get( "crawl-export" );
    Dom.show( exportLink , Boolean( run ) );
    if ( run ) exportLink.setAttribute( "href" , "/api/crawl/" + encodeURIComponent( id ) + "/export.xlsx" );
    if ( !id || !run ) {
      this.total = null;
      this.table.rows( [] );
      Dom.text( Dom.get( "crawl-summary" ) , id ? I18n.get( "crawl.never" ) : "" );
      Missing.counts( { counts: {} , skipped: 0 } , null );
      return;
    }
    let answer;
    try {
      answer = await Api.request( "/api/crawl/" + encodeURIComponent( id ) + "?view=" + this.view + "&limit=2000" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.total = answer.run ? answer.run.novel : null;
    Missing.counts( { counts: {} , skipped: 0 } , null );
    this.table.rows( answer.works );
    const r = answer.run || {};
    Dom.text( Dom.get( "crawl-summary" ) , I18n.get( "crawl.summary" )
      .replace( "{when}" , r.finished_at ? new Date( r.finished_at * 1000 ).toLocaleString() : "" )
      .replace( "{seeds}" , ( r.seeds || 0 ).toLocaleString() ).replace( "{visited}" , ( r.visited || 0 ).toLocaleString() )
      .replace( "{novel}" , ( r.novel || 0 ).toLocaleString() ).replace( "{api}" , ( r.api_used || 0 ).toLocaleString() )
      + ( r.stopped ? " " + I18n.get( "crawl.stopped_note" ) : "" ) + ( ( r.errors || [] ).length ? " " + I18n.get( "crawl.errors_note" ).replace( "{n}" , r.errors.length ) : "" ) );
  },

  columns() {
    return [
      { id: "score" , label: "crawl.col_score" , title: "crawl.score_help" , sort: true , align: "end" , width: 6 , cell: ( row ) => row.score.toFixed( 2 ) },
      { id: "hits" , label: "crawl.col_hits" , title: "crawl.col_hits_title" , sort: true , align: "end" , width: 5 },
      { id: "links" , label: "crawl.col_links" , title: "crawl.col_links_title" , sort: true , align: "end" , width: 5 },
      { id: "depth" , label: "crawl.col_depth" , sort: true , align: "end" , width: 5 },
      { id: "cited_by" , label: "missing.col_cited" , sort: true , align: "end" , width: 7 , cell: ( row ) => ( row.cited_by || 0 ).toLocaleString() },
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , flex: true , lock: true , width: 20 , cell: ( row ) => {
        const children = [ Dom.el( "span" , { class: "paper-title" , text: row.title || row.wid } ) ];
        if ( row.in_library ) children.push( Dom.el( "span" , { class: "badge text-bg-success ms-1" , text: I18n.get( "crawl.in_library" ) } ) );
        return Dom.el( "span" , { children: children } );
      } },
      { id: "from" , label: "crawl.col_from" , width: 14 , cellClass: "small text-body-secondary" , cell: ( row ) => {
        if ( !row.from ) return I18n.get( "crawl.seed" );
        const how = I18n.get( row.how === "cites" ? "crawl.how_cites" : "crawl.how_cited_by" );
        const title = row.from_title || row.from;
        const target = row.from_key
          ? Dom.el( "a" , { text: title , attrs: { href: "#paper/" + encodeURIComponent( row.from_key ) } } )
          : Dom.el( "span" , { text: title } );
        return Dom.el( "span" , { children: [ Dom.el( "span" , { text: how + " " } ) , target ] } );
      } },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( row ) => row.year || "" },
      { id: "links_out" , label: "table.col_links" , width: 9 , cell: ( row ) => Missing.links( row ) },
      { id: "actions" , label: "table.col_actions" , align: "end" , width: 5 , cell: ( row ) => Dom.el( "button" , {
        class: "btn btn-outline-primary btn-sm",
        attrs: { type: "button" , title: I18n.get( "missing.add_title" ) , "aria-label": I18n.get( "missing.add_title" ) },
        children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) ],
        on: { click: () => Missing.addToList( row ) },
      } ) },
    ];
  },
};
