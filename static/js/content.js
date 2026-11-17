// What is ready of each paper, shown the same way wherever a paper appears
// (Library rows, list rows, the Paper screen): the content badges.
//
// The server fills each paper in by itself, one stage at a time (OpenAlex,
// methods, code and dataset links, modality tags), and says so on the
// library's stream: "paper" {key, stage, state}. Every badge strip on the page
// carries its paper's key, so when an event arrives the strips showing that
// paper are fetched again and repainted where they are, with no reload.
//
// The library's stream is opened once here and shared, so every screen that
// wants to hear it does so through Content.on.
const Content = {
  source: null,
  handlers: {},
  // Keys waiting for a fresh badge, gathered for one request.
  stale: new Set(),
  timer: null,
  local: [ "methods" , "code" , "datasets" , "modalities" ],
  refreshSoon: null,

  on( name , handler ) {
    if ( !this.refreshSoon ) this.refreshSoon = this.throttle( () => this.refresh() , 4000 );
    if ( typeof EventSource === "undefined" ) return;
    if ( !this.source ) {
      this.source = new EventSource( "/api/library/stream" );
      this.source.addEventListener( "paper" , ( event ) => this.heard( event ) );
    }
    if ( !this.handlers[ name ] ) {
      this.handlers[ name ] = [];
      if ( name !== "paper" ) {
        this.source.addEventListener( name , ( event ) => this.handlers[ name ].forEach( ( fn ) => fn( this.data( event ) ) ) );
      }
    }
    this.handlers[ name ].push( handler );
  },

  data( event ) {
    try {
      return JSON.parse( event.data );
    } catch ( error ) {
      return {};
    }
  },

  heard( event ) {
    const data = this.data( event );
    ( this.handlers.paper || [] ).forEach( ( fn ) => fn( data ) );
    if ( !data.key ) return;
    if ( !document.querySelector( '[data-content-key="' + CSS.escape( data.key ) + '"]' ) ) return;
    this.stale.add( data.key );
    this.refreshSoon();
  },

  // While the queue works through the library, stage events arrive several a
  // second; every screen that answers them goes through throttle, so the page
  // stays well under the server's rate limit (server.rate_limit_max a minute).
  // fn runs at most once every ms, the last call always landing.
  throttle( fn , ms ) {
    let last = 0;
    let timer = null;
    return function () {
      if ( timer ) return;
      const wait = Math.max( 0 , last + ms - Date.now() );
      timer = setTimeout( () => {
        timer = null;
        last = Date.now();
        fn();
      } , Math.max( wait , 250 ) );
    };
  },

  async refresh() {
    const keys = Array.from( this.stale );
    this.stale.clear();
    if ( !keys.length ) return;
    try {
      const answer = await Api.post( "/api/papers/badges" , { keys: keys } );
      keys.forEach( ( key ) => {
        Dom.all( '[data-content-key="' + CSS.escape( key ) + '"]' ).forEach( ( strip ) => this.paint( strip , answer.badges[ key ] ) );
      } );
    } catch ( error ) { /* the next event tries again */ }
  },

  // A strip of badges for a paper; it repaints itself as stages finish.
  strip( key , badge ) {
    const strip = Dom.el( "span" , { class: "content-badges" , attrs: { "data-content-key": key } } );
    this.paint( strip , badge );
    return strip;
  },

  paint( strip , badge ) {
    Dom.clear( strip );
    this.badges( badge ).forEach( ( node ) => strip.appendChild( node ) );
  },

  chip( text , tone , icon , title ) {
    const children = [];
    if ( icon === "spin" ) {
      children.push( Dom.el( "span" , { class: "spinner-border spinner-border-sm content-spin" , attrs: { "aria-hidden": "true" } } ) );
    } else if ( icon ) {
      children.push( Dom.el( "i" , { class: "bi bi-" + icon , attrs: { "aria-hidden": "true" } } ) );
    }
    children.push( Dom.el( "span" , { text: text } ) );
    const attrs = title ? { title: title } : {};
    return Dom.el( "span" , { class: "badge content-badge " + tone , attrs: attrs , children: children } );
  },

  stageName( stage ) {
    return I18n.get( "content.stage_" + stage );
  },

  // The badges for one paper's summary (null: nothing queued yet).
  badges( badge ) {
    const out = [];
    if ( !badge ) return out;
    const states = badge.states || {};
    const errors = badge.errors || {};
    const oa = states.openalex;
    if ( oa === "done" ) out.push( this.chip( I18n.get( "content.openalex" ) , "text-bg-light border" , "check2" , I18n.get( "content.openalex_done_title" ).replace( "{refs}" , badge.refs || 0 ).replace( "{citers}" , badge.citers || 0 ) ) );
    else if ( oa === "pending" || oa === "running" ) out.push( this.chip( I18n.get( "content.openalex" ) , "text-bg-light border" , "spin" , I18n.get( "content.pending_title" ) ) );
    else if ( oa === "not_found" ) out.push( this.chip( I18n.get( "content.openalex_not_found" ) , "bg-warning-subtle text-warning-emphasis border" , "question-circle" , errors.openalex || "" ) );
    else if ( oa === "failed" ) out.push( this.chip( I18n.get( "content.openalex_failed" ) , "bg-danger-subtle text-danger-emphasis border" , "exclamation-triangle" , errors.openalex || "" ) );

    const reading = this.local.some( ( stage ) => states[ stage ] === "pending" || states[ stage ] === "running" );
    if ( reading ) out.push( this.chip( I18n.get( "content.reading" ) , "text-bg-light border" , "spin" , I18n.get( "content.pending_title" ) ) );
    this.local.forEach( ( stage ) => {
      if ( states[ stage ] === "failed" ) {
        out.push( this.chip( I18n.get( "content.failed" ).replace( "{stage}" , this.stageName( stage ) ) , "bg-danger-subtle text-danger-emphasis border" , "exclamation-triangle" , errors[ stage ] || "" ) );
      }
    } );
    if ( badge.methods ) out.push( this.chip( I18n.get( "content.methods" ) , "text-bg-light border" , "check2" , "" ) );
    if ( badge.code ) out.push( this.chip( I18n.get( "content.code" ).replace( "{n}" , badge.code ) , "bg-success-subtle text-success-emphasis border" , "code-slash" , "" ) );
    if ( badge.data ) out.push( this.chip( I18n.get( "content.data" ).replace( "{n}" , badge.data ) , "bg-info-subtle text-info-emphasis border" , "database" , "" ) );
    if ( badge.figures ) out.push( this.chip( I18n.get( "content.figures" ).replace( "{n}" , badge.figures ) , "text-bg-light border" , "images" , "" ) );
    ( badge.mods || [] ).forEach( ( mod ) => out.push( this.chip( mod , "bg-secondary-subtle text-secondary-emphasis border" , "" , I18n.get( "content.modality_title" ) ) ) );
    return out;
  },

  // Names each cell after its column, for the stacked phone tables (as
  // Pager.label does), reading the heading's own words and not its sort mark.
  label( table ) {
    const heads = Array.from( table.querySelectorAll( "thead th:not([hidden])" ) ).map( ( th ) => {
      const words = th.querySelector( "[data-i18n]" ) || th;
      return words.textContent.trim();
    } );
    Array.from( table.tBodies[ 0 ].rows ).forEach( ( row ) => {
      if ( row.cells.length !== heads.length ) return;
      Array.from( row.cells ).forEach( ( cell , index ) => {
        if ( heads[ index ] ) cell.setAttribute( "data-label" , heads[ index ] );
      } );
    } );
  },

  // A paper's title as a link to its own screen. context: { slug , keys }
  // when it was opened from a list, for the Prev / Next arrows.
  titleLink( paper , context ) {
    const link = Dom.el( "a" , {
      class: "paper-title paper-title-link",
      text: paper.title || paper.key,
      attrs: { href: "#paper/" + encodeURIComponent( paper.key ) },
    } );
    link.addEventListener( "click" , () => {
      PaperView.context = context || null;
    } );
    return link;
  },
};
