// The Status screen: how far each paper's content has got, and what failed.
// The old /status and /errors pages, made from the queue itself rather than
// a scan of the disk, and live: counts move as the queue works.
//
// One card per stage (done / pending / failed / not found, with a bar); below,
// the papers of one stage in one state -- what is still to do, or the
// failures with why, when, and how many tries -- with Retry one or all.
const StatusView = {
  stages: [ "openalex" , "methods" , "code" , "datasets" , "modalities" , "review" , "figures" , "ocr" ],
  heavy: [ "figures" , "ocr" ],
  stage: "openalex",
  state: "errors",
  sort: "added",
  dir: "desc",
  offset: 0,
  pageSize: 100,
  ticket: 0,
  timer: null,
  counts: null,

  init() {
    Dom.show( Dom.get( "status-panel" ) , true );
    Dom.get( "status-state" ).addEventListener( "change" , ( event ) => {
      this.state = event.target.value;
      this.paintFilter();
      this.loadTable();
    } );
    Dom.typed( Dom.get( "status-search" ) , () => this.loadTable() , 250 );
    Dom.onPress( Dom.get( "status-more" ) , () => this.loadTable( true ) );
    Dom.onPress( Dom.get( "status-retry-all" ) , () => this.retryAll() );
    this.table = new DataTable( {
      name: "status",
      holder: Dom.get( "status-table" ),
      menu: Dom.get( "status-columns" ),
      columns: this.columns(),
      sort: [ { col: this.sort , desc: this.dir === "desc" } ],
      onSort: ( sort ) => {
        this.sort = sort[ 0 ].col;
        this.dir = sort[ 0 ].desc ? "desc" : "asc";
        this.loadTable();
      },
      onEnd: () => ( Dom.get( "status-more" ).hidden ? null : this.loadTable( true ) ),
    } );
    this.paintFilter = DataTable.filters( Dom.get( "status-filter" ) ,
      () => ( this.state !== "errors" ? 1 : 0 ),
      () => {
        Dom.get( "status-state" ).value = "errors";
        this.state = "errors";
        this.loadTable();
      } );
    // The counts every few seconds at most; the table only when its own
    // counts moved, and far less often (see Content.throttle).
    const counts = Content.throttle( () => this.loadCounts() , 5000 );
    this.tableSoon = Content.throttle( () => this.loadTable() , 30000 );
    const later = () => {
      if ( Nav.current() !== "status" ) {
        this.stale = true;
        return;
      }
      counts();
    };
    Content.on( "queue" , later );
    window.addEventListener( "hashchange" , () => {
      if ( Nav.current() === "status" && ( this.stale || !this.counts ) ) this.load();
    } );
    if ( Nav.current() === "status" ) this.load();
  },

  async load() {
    this.stale = false;
    await this.loadCounts();
    await this.loadTable();
  },

  async loadCounts() {
    let answer;
    try {
      answer = await Api.request( "/api/content/status" );
    } catch ( error ) {
      return;
    }
    const before = this.counts ? JSON.stringify( this.counts.stages[ this.stage ] ) : "";
    this.counts = answer;
    this.drawCards( answer );
    this.drawLines( answer );
    this.drawTabs( answer );
    if ( before && before !== JSON.stringify( answer.stages[ this.stage ] ) && this.offset <= this.pageSize ) this.tableSoon();
  },

  drawLines( answer ) {
    const library = answer.library;
    Dom.text( Dom.get( "status-library" ) , I18n.get( "status.library_line" )
      .replace( "{papers}" , library.papers.toLocaleString() )
      .replace( "{with_text}" , library.with_text.toLocaleString() )
      .replace( "{no_pdf}" , library.no_pdf.toLocaleString() ) );
    const pool = answer.pool;
    Dom.text( Dom.get( "status-pool" ) , I18n.get( "status.pool_line" )
      .replace( "{all}" , pool.all.toLocaleString() ).replace( "{refs}" , pool.refs.toLocaleString() )
      .replace( "{citing}" , pool.citing.toLocaleString() ).replace( "{papers}" , pool.papers.toLocaleString() ) );
    let note = "";
    if ( !answer.openalex_enabled ) note = I18n.get( "status.openalex_off" );
    else if ( !answer.openalex_key ) note = I18n.get( "status.openalex_no_key" );
    Dom.text( Dom.get( "status-openalex-note" ) , note );
    Dom.show( Dom.get( "status-openalex-note" ) , Boolean( note ) );
    this.drawWorkers( answer.workers || [] );
  },

  // Whether the figures / OCR worker is running, and what it is on.
  drawWorkers( workers ) {
    const holder = Dom.get( "status-workers" );
    Dom.clear( holder );
    const alive = workers.filter( ( worker ) => worker.alive );
    if ( !alive.length ) holder.appendChild( Dom.el( "li" , { class: "text-body-secondary" , text: I18n.get( "status.worker_none" ) } ) );
    workers.forEach( ( worker ) => {
      if ( !worker.alive ) {
        holder.appendChild( Dom.el( "li" , { class: "text-body-secondary" , text: I18n.get( "status.worker_gone" ).replace( "{host}" , () => worker.host ).replace( "{ago}" , Dom.ago( new Date( worker.beat * 1000 ).toISOString() ) ) } ) );
        return;
      }
      const doing = worker.doing ? worker.doing.replace( /^(\w+) / , ( m , stage ) => Content.stageName( stage ) + ": " ) : I18n.get( "status.worker_idle" );
      const line = Dom.el( "li" , { children: [
        Dom.el( "span" , { class: "spinner-grow spinner-grow-sm text-success me-1" , attrs: { "aria-hidden": "true" } } ),
        Dom.el( "span" , { text: I18n.get( "status.worker_line" ).replace( "{host}" , () => worker.host ).replace( "{pid}" , worker.pid ).replace( "{doing}" , () => doing ) } ),
      ] } );
      holder.appendChild( line );
      if ( worker.note ) holder.appendChild( Dom.el( "li" , { class: "text-warning-emphasis" , text: I18n.get( "status.worker_note" ).replace( "{note}" , () => worker.note ) } ) );
    } );
  },

  drawCards( answer ) {
    const holder = Dom.get( "status-cards" );
    Dom.clear( holder );
    this.stages.forEach( ( stage ) => {
      const counts = answer.stages[ stage ] || {};
      const total = [ "done" , "pending" , "running" , "failed" , "not_found" ].reduce( ( sum , state ) => sum + ( counts[ state ] || 0 ) , 0 );
      const settled = ( counts.done || 0 ) + ( counts.not_found || 0 );
      const percent = total ? Math.floor( ( settled / total ) * 100 ) : 0;
      const bar = Dom.el( "div" , { class: "progress-bar" } );
      bar.style.width = percent + "%";
      const heavy = this.heavy.includes( stage );
      const running = heavy
        ? ( answer.workers || [] ).some( ( worker ) => worker.alive && ( worker.doing || "" ).startsWith( stage + " " ) )
        : Object.values( answer.running || {} ).length && ( answer.running.net && stage === "openalex" || answer.running.local && stage !== "openalex" );
      const line = ( key , n ) => Dom.el( "li" , { class: "d-flex justify-content-between" , children: [
        Dom.el( "span" , { text: I18n.get( "content.state_" + key ) } ) , Dom.el( "span" , { class: "fw-semibold" , text: ( n || 0 ).toLocaleString() } ),
      ] } );
      const button = Dom.el( "button" , {
        class: "card h-100 text-start status-stage w-100" + ( stage === this.stage ? " border-primary" : "" ),
        attrs: { type: "button" , "aria-pressed": String( stage === this.stage ) },
        on: { click: () => { this.stage = stage; this.drawCards( answer ); this.drawTabs( answer ); this.loadTable(); } },
        children: [ Dom.el( "div" , { class: "card-body" , children: [
          Dom.el( "div" , { class: "d-flex align-items-center gap-2 mb-2" , children: [
            Dom.el( "h3" , { class: "h6 mb-0" , text: Content.stageName( stage ) } ),
            running ? Dom.el( "span" , { class: "spinner-border spinner-border-sm text-secondary" , attrs: { "aria-hidden": "true" } } ) : null,
            Dom.el( "span" , { class: "ms-auto small text-body-secondary" , text: percent + "%" } ),
          ].filter( Boolean ) } ),
          Dom.el( "div" , { class: "progress mb-2" , attrs: { role: "progressbar" , "aria-valuenow": String( percent ) , "aria-valuemin": "0" , "aria-valuemax": "100" } , children: [ bar ] } ),
          Dom.el( "ul" , { class: "list-unstyled small mb-0" , children: [
            line( "done" , counts.done ), line( "pending" , ( counts.pending || 0 ) + ( counts.running || 0 ) ),
            line( "failed" , counts.failed ), line( "not_found" , counts.not_found ),
          ] } ),
        ] } ) ],
      } );
      holder.appendChild( Dom.el( "div" , { class: "col" , children: [ button ] } ) );
    } );
  },

  drawTabs( answer ) {
    Dom.text( Dom.get( "status-table-heading" ) , I18n.get( "status.table_heading" ).replace( "{stage}" , Content.stageName( this.stage ) ) );
    const counts = answer.stages[ this.stage ] || {};
    const options = {
      errors: ( counts.failed || 0 ) + ( counts.not_found || 0 ), failed: counts.failed || 0, not_found: counts.not_found || 0,
      unfinished: ( counts.pending || 0 ) + ( counts.running || 0 ) + ( counts.failed || 0 ), pending: ( counts.pending || 0 ) + ( counts.running || 0 ),
      done: counts.done || 0,
    };
    Dom.all( "#status-state option" ).forEach( ( option ) => {
      Dom.text( option , I18n.get( "status.show_" + option.value ).replace( "{n}" , ( options[ option.value ] || 0 ).toLocaleString() ) );
    } );
  },

  params( offset ) {
    const params = new URLSearchParams( { stage: this.stage , state: this.state , sort: this.sort , dir: this.dir , limit: String( this.pageSize ) , offset: String( offset ) } );
    const text = Dom.get( "status-search" ).value.trim();
    if ( text ) params.set( "q" , text );
    return params;
  },

  async loadTable( more ) {
    const ticket = ++this.ticket;
    const offset = more ? this.offset : 0;
    let answer;
    try {
      answer = await Api.request( "/api/content/papers?" + this.params( offset ) );
    } catch ( error ) {
      if ( ticket === this.ticket ) Dom.toast( error.message , "error" );
      return;
    }
    if ( ticket !== this.ticket ) return;
    this.table.rows( answer.papers , Boolean( more ) );
    this.offset = answer.next == null ? offset + answer.papers.length : answer.next;
    Dom.show( Dom.get( "status-more" ) , answer.next != null );
    Dom.show( Dom.get( "status-empty" ) , answer.total === 0 );
    Dom.text( Dom.get( "status-total" ) , I18n.get( "table.showing" ).replace( "{shown}" , this.offset.toLocaleString() ).replace( "{total}" , answer.total.toLocaleString() ) );
    const retryable = [ "errors" , "failed" , "not_found" ].includes( this.state ) && answer.total > 0;
    Dom.show( Dom.get( "status-retry-all" ) , retryable );
  },

  when( seconds ) {
    return Dom.when( seconds ? new Date( seconds * 1000 ).toISOString() : "" , "" );
  },

  // The table's columns; the server sorts (see the papers route's sort).
  columns() {
    return [
      { id: "title" , label: "status.col_paper" , sort: true , firstDesc: false , flex: true , lock: true , width: 16 , cell: ( row ) => Content.titleLink( row ) },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( row ) => row.year || "" },
      { id: "journal" , label: "table.col_journal" , sort: true , firstDesc: false , width: 12 , hide: true , cellClass: "small text-body-secondary" , cell: ( row ) => row.journal || "" },
      { id: "added" , label: "table.col_added" , sort: true , width: 8 , hide: true , cellClass: "small text-nowrap" , cell: ( row ) => Dom.when( row.added || "" , "" ) },
      { id: "links" , label: "table.col_links" , width: 8 , cell: ( row ) => this.links( row ) },
      { id: "state" , label: "status.col_state" , sort: true , firstDesc: false , width: 8 , cell: ( row ) => PaperView.stateBadge( row.state ) },
      { id: "error" , label: "status.col_error" , sort: true , firstDesc: false , width: 14 , cellClass: "small" , cell: ( row ) => row.error || "" },
      { id: "first_failed" , label: "status.col_first" , sort: true , width: 8 , cellClass: "small text-nowrap" , cell: ( row ) => this.when( row.first_failed ) },
      { id: "last_failed" , label: "status.col_last" , sort: true , width: 8 , cellClass: "small text-nowrap" , cell: ( row ) => this.when( row.last_failed ) },
      { id: "attempts" , label: "status.col_attempts" , sort: true , align: "end" , width: 5 , cell: ( row ) => String( row.attempts || 0 ) },
      { id: "actions" , label: "table.col_actions" , align: "end" , width: 6 , cell: ( row ) => this.retryButton( row ) },
    ];
  },

  links( row ) {
    const links = [];
    if ( row.doi ) links.push( PaperLinks.link( "https://doi.org/" + row.doi , "links.doi" , "links.doi_title" ) );
    if ( row.doi ) links.push( PaperLinks.link( "https://api.openalex.org/works/https://doi.org/" + row.doi , "missing.openalex" , "missing.openalex_title" ) );
    return Dom.el( "span" , { class: "paper-links small" , children: links } );
  },

  retryButton( row ) {
    if ( row.state !== "failed" && row.state !== "not_found" ) return null;
    return Dom.el( "button" , {
      class: "btn btn-outline-secondary btn-sm",
      text: I18n.get( "content.retry" ),
      on: { click: async () => {
        await Api.post( "/api/papers/retry" , { key: row.key , stage: this.stage } );
        await this.load();
      } },
    } );
  },

  async retryAll() {
    if ( !( await Dom.confirm( I18n.get( "status.retry_all_confirm" ).replace( "{stage}" , Content.stageName( this.stage ) ) ) ) ) return;
    const answer = await Api.post( "/api/papers/retry" , { stage: this.stage } );
    Dom.toast( I18n.get( "status.retried" ).replace( "{n}" , answer.queued ) , "success" );
    await this.load();
  },
};
