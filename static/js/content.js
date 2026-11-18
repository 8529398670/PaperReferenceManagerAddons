// What is ready of each paper, shown the same way wherever a paper appears
// (Library rows, list rows, the Paper screen): the content badges.
//
// The server fills each paper in by itself, one stage at a time (OpenAlex,
// methods, code and dataset links, modality tags), and says so on the
// library's stream: "paper" {key, stage, state}. Every badge strip on the page
// carries its paper's key, so when an event arrives the strips showing that
// paper are fetched again and repainted where they are, with no reload.
//
// The library's stream is opened once here (through Live, which shares it with
// the other tabs), so every screen that wants to hear it does so through Content.on.
const Content = {
  source: null,
  handlers: {},
  // Keys waiting for a fresh badge, gathered for one request.
  stale: new Set(),
  timer: null,
  local: [ "methods" , "code" , "datasets" , "modalities" , "review" ],
  refreshSoon: null,

  on( name , handler ) {
    if ( !this.refreshSoon ) this.refreshSoon = this.throttle( () => this.refresh() , 4000 );
    if ( typeof EventSource === "undefined" ) return;
    if ( !this.source ) {
      this.source = "/api/library/stream";
      Live.on( this.source , "paper" , ( event ) => this.heard( event ) );
    }
    if ( !this.handlers[ name ] ) {
      this.handlers[ name ] = [];
      if ( name !== "paper" ) {
        Live.on( this.source , name , ( event ) => this.handlers[ name ].forEach( ( fn ) => fn( this.data( event ) ) ) );
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
    const key = CSS.escape( data.key );
    if ( !document.querySelector( '[data-content-key="' + key + '"], [data-content-links="' + key + '"]' ) ) return;
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
        Dom.all( '[data-content-links="' + CSS.escape( key ) + '"]' ).forEach( ( span ) => this.paintLinks( span , answer.badges[ key ] ) );
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
    const key = strip.getAttribute( "data-content-key" );
    const nodes = strip.hasAttribute( "data-labels" ) ? this.labels( strip , badge ) : this.badges( badge , key );
    nodes.forEach( ( node ) => strip.appendChild( node ) );
  },

  // One strip of coloured labels for a paper (the Lists board): its links
  // and what the stages made, in one fixed order -- DOI, Proxy, PDF,
  // Figures, MD, Methods, Code, Datasets -- then OpenAlex and stage states,
  // then modalities. paper needs key, doi and has_pdf; they ride on the
  // strip so it can repaint itself. content undefined: the paper is not in
  // the library, so only its DOI links show.
  labelStrip( paper , content ) {
    const strip = Dom.el( "span" , { class: "content-badges" , attrs: {
      "data-content-key": paper.key || "",
      "data-labels": "",
      "data-doi": paper.doi || "",
      "data-pdf": paper.has_pdf ? "1" : "",
    } } );
    this.paint( strip , content );
    return strip;
  },

  labels( strip , badge ) {
    const key = strip.getAttribute( "data-content-key" );
    const doi = strip.getAttribute( "data-doi" );
    const b = badge || {};
    const out = [];
    const tone = {
      doi: "bg-primary-subtle text-primary-emphasis border border-primary-subtle",
      proxy: "bg-primary-subtle text-primary-emphasis border border-primary-subtle",
      pdf: "content-badge-pdf border",
      figures: "bg-warning-subtle text-warning-emphasis border border-warning-subtle",
      md: "bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle",
      methods: "bg-dark-subtle text-dark-emphasis border border-dark-subtle",
      code: "bg-success-subtle text-success-emphasis border border-success-subtle",
      data: "bg-info-subtle text-info-emphasis border border-info-subtle",
    };
    if ( doi ) {
      out.push( this.chip( I18n.get( "links.doi" ) , tone.doi , "link-45deg" , I18n.get( "links.doi_title" ) , "https://doi.org/" + doi ) );
      if ( PaperLinks.proxyUrl ) {
        out.push( this.chip( I18n.get( "links.proxy" ) , tone.proxy , "building" , I18n.get( "links.proxy_title" ) , PaperLinks.proxyUrl.replace( "{doi}" , () => doi ) ) );
      }
    }
    if ( key && strip.getAttribute( "data-pdf" ) ) {
      out.push( this.chip( I18n.get( "links.pdf" ) , tone.pdf , "file-earmark-pdf" , I18n.get( "links.pdf_title" ) , "/api/paper/pdf?key=" + encodeURIComponent( key ) ) );
    }
    if ( !badge || !key ) return out;
    if ( b.figures ) out.push( this.chip( I18n.get( "content.figures" ).replace( "{n}" , b.figures ) , tone.figures , "images" , I18n.get( "links.figures_title" ) , this.href( key , "montage" ) ) );
    if ( b.has_text || b.methods ) out.push( this.chip( I18n.get( "links.md" ) , tone.md , "file-earmark-text" , I18n.get( "links.md_title" ) , this.href( key , "md" ) ) );
    if ( b.methods ) out.push( this.chip( I18n.get( "links.methods" ) , tone.methods , "journal-text" , I18n.get( "links.methods_title" ) , this.href( key , "methods" ) ) );
    if ( b.code ) out.push( this.chip( I18n.get( "content.code" ).replace( "{n}" , b.code ) , tone.code , "code-slash" , I18n.get( "content.found_title" ) , this.href( key , "found" ) ) );
    if ( b.data ) out.push( this.chip( I18n.get( "content.data" ).replace( "{n}" , b.data ) , tone.data , "database" , I18n.get( "content.found_title" ) , this.href( key , "found" ) ) );
    // The rest of the usual badges: OpenAlex, stage states, modalities --
    // everything badges() makes but the ones drawn above.
    const shown = new Set( [ "methods" , "code" , "data" , "figures" ] );
    return out.concat( this.badges( b , key , shown ) );
  },

  // The links to what the stages made, as the old app had them after PDF:
  // Figures (the montage), MD (the whole text) and Methods. Each shows once
  // there is something to open; they repaint with the badges.
  links( key , badge ) {
    const span = Dom.el( "span" , { class: "paper-links" , attrs: { "data-content-links": key } } );
    this.paintLinks( span , badge );
    return span;
  },

  paintLinks( span , badge ) {
    const key = span.getAttribute( "data-content-links" );
    const links = [];
    const b = badge || {};
    if ( b.figures ) links.push( PaperLinks.link( this.href( key , "montage" ) , "links.figures" , "links.figures_title" ) );
    if ( b.has_text || b.methods ) links.push( PaperLinks.link( this.href( key , "md" ) , "links.md" , "links.md_title" ) );
    if ( b.methods ) links.push( PaperLinks.link( this.href( key , "methods" ) , "links.methods" , "links.methods_title" ) );
    span.replaceChildren( ...links );
    span.hidden = links.length === 0;
  },

  // Where each thing about a paper opens: a file in a new tab (montage, md,
  // methods), or a card of its Paper screen (#paper/<key>/<card>).
  href( key , what ) {
    const k = encodeURIComponent( key );
    if ( what === "montage" ) return "/api/figures/image?n=0&key=" + k;
    if ( what === "md" || what === "methods" ) return "/api/paper/text?part=" + what + "&key=" + k;
    return "#paper/" + k + "/" + what;
  },

  // A badge that opens what it names (href from Content.href); a file opens
  // in a new tab, a Paper screen card in this one.
  chip( text , tone , icon , title , href ) {
    const children = [];
    if ( icon === "spin" ) {
      children.push( Dom.el( "span" , { class: "spinner-border spinner-border-sm content-spin" , attrs: { "aria-hidden": "true" } } ) );
    } else if ( icon ) {
      children.push( Dom.el( "i" , { class: "bi bi-" + icon , attrs: { "aria-hidden": "true" } } ) );
    }
    children.push( Dom.el( "span" , { text: text } ) );
    const attrs = title ? { title: title } : {};
    if ( !href ) return Dom.el( "span" , { class: "badge content-badge " + tone , attrs: attrs , children: children } );
    attrs.href = href;
    if ( !href.startsWith( "#" ) ) {
      attrs.target = "_blank";
      attrs.rel = "noopener";
    }
    return Dom.el( "a" , { class: "badge content-badge content-badge-link " + tone , attrs: attrs , children: children } );
  },

  stageName( stage ) {
    return I18n.get( "content.stage_" + stage );
  },

  // The badges for one paper's summary (null: nothing queued yet). With
  // key, each badge links to what it names.
  badges( badge , key , skip ) {
    const out = [];
    const omit = skip || new Set();
    if ( !badge ) return out;
    const to = ( what ) => ( key ? this.href( key , what ) : "" );
    const states = badge.states || {};
    const errors = badge.errors || {};
    const oa = states.openalex;
    if ( oa === "done" ) out.push( this.chip( I18n.get( "content.openalex" ) , "text-bg-light border" , "check2" , I18n.get( "content.openalex_done_title" ).replace( "{refs}" , badge.refs || 0 ).replace( "{citers}" , badge.citers || 0 ) , to( "network" ) ) );
    else if ( oa === "pending" || oa === "running" ) out.push( this.chip( I18n.get( "content.openalex" ) , "text-bg-light border" , "spin" , I18n.get( "content.pending_title" ) , to( "stages" ) ) );
    else if ( oa === "not_found" ) out.push( this.chip( I18n.get( "content.openalex_not_found" ) , "bg-warning-subtle text-warning-emphasis border" , "question-circle" , errors.openalex || "" , to( "stages" ) ) );
    else if ( oa === "failed" ) out.push( this.chip( I18n.get( "content.openalex_failed" ) , "bg-danger-subtle text-danger-emphasis border" , "exclamation-triangle" , errors.openalex || "" , to( "stages" ) ) );

    const reading = this.local.some( ( stage ) => states[ stage ] === "pending" || states[ stage ] === "running" );
    if ( reading ) out.push( this.chip( I18n.get( "content.reading" ) , "text-bg-light border" , "spin" , I18n.get( "content.pending_title" ) , to( "stages" ) ) );
    this.local.forEach( ( stage ) => {
      if ( states[ stage ] === "failed" ) {
        out.push( this.chip( I18n.get( "content.failed" ).replace( "{stage}" , this.stageName( stage ) ) , "bg-danger-subtle text-danger-emphasis border" , "exclamation-triangle" , errors[ stage ] || "" , to( "stages" ) ) );
      }
    } );
    if ( !omit.has( "methods" ) && badge.methods ) out.push( this.chip( I18n.get( "content.methods" ) , "text-bg-light border" , "check2" , I18n.get( "links.methods_title" ) , to( "methods" ) ) );
    if ( !omit.has( "code" ) && badge.code ) out.push( this.chip( I18n.get( "content.code" ).replace( "{n}" , badge.code ) , "bg-success-subtle text-success-emphasis border" , "code-slash" , I18n.get( "content.found_title" ) , to( "found" ) ) );
    if ( !omit.has( "data" ) && badge.data ) out.push( this.chip( I18n.get( "content.data" ).replace( "{n}" , badge.data ) , "bg-info-subtle text-info-emphasis border" , "database" , I18n.get( "content.found_title" ) , to( "found" ) ) );
    if ( !omit.has( "figures" ) && badge.figures ) out.push( this.chip( I18n.get( "content.figures" ).replace( "{n}" , badge.figures ) , "text-bg-light border" , "images" , I18n.get( "links.figures_title" ) , to( "montage" ) ) );
    ( badge.mods || [] ).forEach( ( mod ) => out.push( this.chip( mod , "bg-secondary-subtle text-secondary-emphasis border" , "" , I18n.get( "content.modality_title" ) , to( "sections" ) ) ) );
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
