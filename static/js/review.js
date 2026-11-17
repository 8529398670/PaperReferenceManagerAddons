// The Review screen: the old /review and /review-missing as one page with a
// pool switch.
//
// Library (#review)          every paper on a list or with a picked figure,
//                            screened against the three criteria in full text
//                            (/api/review/library). Included and borderline
//                            papers are cards; the excluded are a table with
//                            their reasons; the dataset consensus is last.
// Missing (#review/missing)  the papers you do not have, screened on their
//                            title and abstract (/api/review/missing): the
//                            works screened in, the near misses, the excluded
//                            tallied by reason, and how far an abstract screen
//                            can be trusted, measured against your own papers.
//
// There is no build: the server screens one paper (or a batch of works) at a
// time, and the page reloads, throttled, as its events arrive. A card opened
// asks for that paper's review in full: every value with the sentence it
// came from, and the other values the paper states.
//
// Every row is on the page, so filters and sorting happen here, and the
// export is exactly the cards shown, in that order.
const ReviewView = {
  pool: "library",
  data: { library: null , missing: null },
  loaded: { library: false , missing: false },
  stale: { library: false , missing: false },
  checks: new Set(),
  shown: [],
  limit: 50,
  PAGE: 50,
  open: new Set(),
  details: new Map(),

  init() {
    Dom.show( Dom.get( "review-panel" ) , true );
    Dom.typed( Dom.get( "review-search" ) , () => this.draw( true ) , 200 );
    [ "review-priority" , "review-task" , "review-pool-from" ].forEach( ( id ) => Dom.get( id ).addEventListener( "change" , () => this.draw( true ) ) );
    Dom.all( "[data-review-check]" ).forEach( ( box ) => box.addEventListener( "change" , () => {
      const name = box.getAttribute( "data-review-check" );
      if ( box.checked ) this.checks.add( name );
      else this.checks.delete( name );
      this.draw( true );
    } ) );
    Dom.get( "review-borderline-only" ).addEventListener( "change" , () => this.draw( true ) );
    Dom.get( "review-sort" ).addEventListener( "change" , () => this.draw( true ) );
    Dom.onPress( Dom.get( "review-reverse" ) , () => {
      const button = Dom.get( "review-reverse" );
      button.setAttribute( "aria-pressed" , button.getAttribute( "aria-pressed" ) === "true" ? "false" : "true" );
      button.classList.toggle( "active" , button.getAttribute( "aria-pressed" ) === "true" );
      this.draw( true );
    } );
    Dom.onPress( Dom.get( "review-more" ) , () => {
      this.limit += this.PAGE;
      this.draw( false );
    } );
    this.paintFilter = DataTable.filters( Dom.get( "review-filter" ) ,
      () => this.checks.size + [ "review-priority" , "review-task" , "review-pool-from" ].filter( ( id ) => Dom.get( id ).value ).length,
      () => {
        this.checks.clear();
        Dom.all( "[data-review-check]" ).forEach( ( box ) => { box.checked = false; } );
        [ "review-priority" , "review-task" , "review-pool-from" ].forEach( ( id ) => { Dom.get( id ).value = ""; } );
        this.draw( true );
      } );
    Dom.onPress( Dom.get( "review-export-json" ) , () => this.exportJson() );
    Dom.onPress( Dom.get( "review-export-csv" ) , () => this.exportCsv() );

    const soon = {
      library: Content.throttle( () => this.changed( "library" ) , 8000 ),
      missing: Content.throttle( () => this.changed( "missing" ) , 15000 ),
    };
    Content.on( "paper" , ( data ) => { if ( data.stage === "review" ) soon.library(); } );
    Content.on( "review_pool" , () => soon.missing() );
    window.addEventListener( "hashchange" , () => this.route() );
    this.route();
  },

  // #review or #review/missing: which pool, loaded when first shown.
  route() {
    if ( Nav.current() !== "review" ) return;
    const pool = window.location.hash.replace( /^#/ , "" ).split( "/" )[ 1 ] === "missing" ? "missing" : "library";
    if ( pool !== this.pool ) {
      this.pool = pool;
      this.open.clear();
      this.limit = this.PAGE;
      this.setupControls();
      if ( this.data[ pool ] ) this.paint();
      else this.blank();
    }
    Dom.all( "[data-review-pool]" ).forEach( ( tab ) => {
      const on = tab.getAttribute( "data-review-pool" ) === this.pool;
      tab.classList.toggle( "active" , on );
      if ( on ) tab.setAttribute( "aria-current" , "true" );
      else tab.removeAttribute( "aria-current" );
    } );
    if ( !this.loaded[ pool ] || this.stale[ pool ] ) this.load( pool );
  },

  changed( pool ) {
    if ( Nav.current() === "review" && this.pool === pool ) this.load( pool );
    else this.stale[ pool ] = true;
  },

  async load( pool ) {
    this.stale[ pool ] = false;
    let answer;
    try {
      answer = await Api.request( pool === "missing" ? "/api/review/missing" : "/api/review/library" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    const first = !this.loaded[ pool ];
    this.loaded[ pool ] = true;
    this.data[ pool ] = answer;
    if ( pool === "library" ) this.tasks = answer.tasks;
    if ( pool !== this.pool ) return;
    // A reload keeps open cards' details, but the values may have moved.
    if ( !first ) this.details.clear();
    if ( first ) this.setupControls();
    this.paint();
  },

  // The pool's own filters and sort options.
  setupControls() {
    const missing = this.pool === "missing";
    Dom.all( "[data-review-only]" ).forEach( ( node ) => Dom.show( node , node.getAttribute( "data-review-only" ) === this.pool ) );
    Dom.show( Dom.get( "review-borderline-only" ).nextElementSibling , !missing );
    Dom.show( Dom.get( "review-borderline-only" ) , !missing );
    const sort = Dom.get( "review-sort" );
    const before = sort.value;
    Dom.clear( sort );
    const options = missing
      ? [ [ "" , "review.sort_default_missing" ] , [ "pubdate" , "review.sort_pubdate" ] , [ "year" , "review.sort_year" ] , [ "cites" , "review.sort_cites" ] ,
        [ "title" , "review.sort_title" ] , [ "model" , "review.sort_model" ] , [ "priority" , "review.sort_default" ] ]
      : [ [ "" , "review.sort_default" ] , [ "added" , "review.sort_added" ] , [ "pubdate" , "review.sort_pubdate" ] , [ "year" , "review.sort_year" ] ,
        [ "cites" , "review.sort_cites" ] , [ "title" , "review.sort_title" ] , [ "model" , "review.sort_model" ] ];
    options.forEach( ( [ value , label ] ) => sort.appendChild( Dom.el( "option" , { text: I18n.get( label ) , attrs: { value: value } } ) ) );
    sort.value = options.some( ( o ) => o[ 0 ] === before ) ? before : "";
    this.fillSelects();
  },

  fillSelects() {
    const tasks = ( this.data.library || {} ).tasks || this.tasks || [];
    const priority = Dom.get( "review-priority" );
    const keepP = priority.value;
    Dom.clear( priority );
    priority.appendChild( Dom.el( "option" , { text: I18n.get( "review.priority_any" ) , attrs: { value: "" } } ) );
    const byPriority = new Map();
    tasks.forEach( ( t ) => byPriority.set( t.priority , ( byPriority.get( t.priority ) || [] ).concat( [ t.name ] ) ) );
    const unclassified = ( this.data.library || {} ).unclassified_priority;
    if ( unclassified != null && !byPriority.has( unclassified ) ) byPriority.set( unclassified , [ "unclassified" ] );
    Array.from( byPriority.keys() ).sort( ( a , b ) => a - b ).forEach( ( n ) => priority.appendChild( Dom.el( "option" , {
      text: I18n.get( "review.priority_option" ).replace( "{n}" , n ).replace( "{task}" , () => byPriority.get( n ).join( ", " ) ),
      attrs: { value: String( n ) },
    } ) ) );
    priority.value = keepP;
    const task = Dom.get( "review-task" );
    const keepT = task.value;
    Dom.clear( task );
    task.appendChild( Dom.el( "option" , { text: I18n.get( "review.task_any" ) , attrs: { value: "" } } ) );
    tasks.concat( [ { name: "unclassified" } ] ).forEach( ( t ) => task.appendChild( Dom.el( "option" , { text: t.name , attrs: { value: t.name } } ) ) );
    task.value = keepT;
  },

  // A pool not loaded yet: nothing of the other one stays on screen meanwhile.
  blank() {
    [ "review-list" , "review-counts" , "review-calibration" ].forEach( ( id ) => Dom.clear( Dom.get( id ) ) );
    Dom.get( "review-list" ).appendChild( Dom.el( "p" , { class: "list-group-item text-body-secondary mb-0" , text: I18n.get( "review.loading" ) } ) );
    [ "review-progress" , "review-more" , "review-empty" , "review-excluded-card" , "review-near-card" , "review-tally-card" , "review-consensus-card" ]
      .forEach( ( id ) => Dom.show( Dom.get( id ) , false ) );
    Dom.text( Dom.get( "review-count" ) , "" );
  },

  // -- the header ---------------------------------------------------------------------

  paint() {
    const data = this.data[ this.pool ];
    if ( !data ) return;
    if ( !this.data.library && this.pool === "missing" ) {
      // The task list (for the filters) comes with the library's review.
      Api.request( "/api/review/library" ).then( ( answer ) => {
        this.data.library = answer;
        this.loaded.library = true;
        this.fillSelects();
      } ).catch( () => {} );
    }
    this.paintCounts( data );
    const criteria = Dom.get( "review-criteria" );
    Dom.clear( criteria );
    ( this.pool === "missing" ? data.criteria : data.criteria ).forEach( ( text ) => criteria.appendChild( Dom.el( "li" , { text: text } ) ) );
    Dom.text( Dom.get( "review-criteria-note" ) , I18n.get( "review.criteria_missing_note" ) );
    Dom.show( Dom.get( "review-criteria-note" ) , this.pool === "missing" );
    const problem = Dom.get( "review-problem" );
    Dom.text( problem , this.pool === "library" ? data.problem || "" : "" );
    Dom.show( problem , this.pool === "library" && Boolean( data.problem ) );
    this.paintCalibration( data );
    this.draw( false );
    this.paintBottom( data );
  },

  pill( text , tone , title ) {
    const pill = Dom.el( "span" , { class: "badge rounded-pill " + tone , text: text } );
    if ( title ) pill.title = title;
    return pill;
  },

  paintCounts( data ) {
    const holder = Dom.get( "review-counts" );
    Dom.clear( holder );
    const c = data.counts;
    const n = ( key , value ) => I18n.get( key ).replace( "{n}" , ( value || 0 ).toLocaleString() );
    const progress = Dom.get( "review-progress" );
    if ( this.pool === "library" ) {
      holder.appendChild( this.pill( n( "review.n_included" , c.included ) , "text-bg-success" ) );
      holder.appendChild( this.pill( n( "review.n_borderline" , c.borderline ) , "text-bg-warning" , I18n.get( "review.borderline_title" ) ) );
      holder.appendChild( this.pill( n( "review.n_excluded" , c.excluded ) , "text-bg-secondary" ) );
      if ( c.waiting ) holder.appendChild( this.pill( n( "review.n_waiting" , c.waiting ) , "text-bg-light border" , I18n.get( "review.waiting_title" ) ) );
      if ( c.failed ) holder.appendChild( this.pill( n( "review.n_failed" , c.failed ) , "text-bg-danger" ) );
      if ( c.stale ) holder.appendChild( this.pill( n( "review.n_stale" , c.stale ) , "text-bg-light border" , I18n.get( "review.stale_title" ) ) );
      Dom.show( progress , false );
      return;
    }
    holder.appendChild( this.pill( n( "review.n_included" , c.included ) , "text-bg-success" ) );
    holder.appendChild( this.pill( n( "review.n_near" , c.near_misses ) , "text-bg-warning" ) );
    holder.appendChild( this.pill( n( "review.n_excluded" , c.excluded ) , "text-bg-secondary" ) );
    holder.appendChild( this.pill( n( "review.n_no_abstract" , c.no_abstract ) , "text-bg-light border" ) );
    const p = data.progress;
    const parts = [ ( p.screened < p.total ? I18n.get( "review.pool_progress" ) : I18n.get( "review.pool_done" ) )
      .replace( "{screened}" , p.screened.toLocaleString() ).replace( "{total}" , p.total.toLocaleString() ) ];
    const filling = data.filling || {};
    if ( filling.filled < filling.papers ) {
      parts.unshift( I18n.get( "review.pool_filling" ).replace( "{filled}" , filling.filled.toLocaleString() ).replace( "{papers}" , filling.papers.toLocaleString() ) );
    }
    if ( data.papers_cut ) parts.push( I18n.get( "review.pool_cut" ).replace( "{n}" , data.papers_cut.toLocaleString() ) );
    Dom.text( progress , parts.join( " " ) );
    Dom.show( progress , true );
  },

  paintCalibration( data ) {
    const holder = Dom.get( "review-calibration" );
    Dom.clear( holder );
    Dom.show( holder , this.pool === "missing" );
    if ( this.pool !== "missing" ) return;
    const cal = data.calibration || {};
    const pct = ( value ) => String( Math.round( value * 100 ) );
    const cells = [];
    if ( cal.recall != null ) {
      cells.push( [ I18n.get( "review.recall" ).replace( "{pct}" , pct( cal.recall ) ) ,
        I18n.get( "review.recall_basis" ).replace( "{total}" , cal.recall_total ).replace( "{found}" , cal.recall_found ) ] );
    } else {
      cells.push( [ I18n.get( "review.recall" ).replace( "{pct}" , "–" ) , I18n.get( "review.recall_none" ) ] );
    }
    if ( cal.precision != null ) {
      cells.push( [ I18n.get( "review.precision" ).replace( "{pct}" , pct( cal.precision ) ) ,
        I18n.get( "review.precision_basis" ).replace( "{passed}" , cal.precision_passed ).replace( "{agreed}" , cal.precision_agreed ) ] );
    } else {
      cells.push( [ I18n.get( "review.precision_configured" ).replace( "{pct}" , pct( cal.configured_precision || 0 ) ) , cal.configured_precision_why || "" ] );
    }
    const row = Dom.el( "div" , { class: "row g-3" , children: cells.map( ( [ head , body ] ) => Dom.el( "div" , { class: "col-12 col-md-6" , children: [
      Dom.el( "div" , { class: "fs-5 fw-semibold" , text: head } ),
      Dom.el( "div" , { class: "small text-body-secondary" , text: body } ),
    ] } ) ) } );
    const foot = [];
    if ( cal.measured_over ) foot.push( I18n.get( "review.measured_over" ).replace( "{n}" , cal.measured_over ) );
    if ( cal.caveat ) foot.push( cal.caveat );
    holder.appendChild( Dom.el( "section" , { class: "card" , children: [
      Dom.el( "div" , { class: "card-header" , children: [ Dom.el( "h3" , { class: "h6 mb-0" , text: I18n.get( "review.calibration" ) } ) ] } ),
      Dom.el( "div" , { class: "card-body" , children: [ row , Dom.el( "p" , { class: "small mb-0 mt-3" , text: foot.join( " " ) } ) ] } ),
    ] } ) );
  },

  // -- filtering and sorting --------------------------------------------------------------

  rows() {
    const data = this.data[ this.pool ];
    if ( !data ) return [];
    if ( this.pool === "missing" ) return data.papers;
    return data.papers.filter( ( row ) => row.state === "included" || row.state === "borderline" );
  },

  matches( row ) {
    const priority = Dom.get( "review-priority" ).value;
    if ( priority && String( row.priority ) !== priority ) return false;
    const task = Dom.get( "review-task" ).value;
    if ( task && ( row.task || "unclassified" ) !== task ) return false;
    if ( this.pool === "library" ) {
      if ( Dom.get( "review-borderline-only" ).checked && row.state !== "borderline" ) return false;
      if ( this.checks.has( "list" ) && !( row.lists || [] ).length ) return false;
      if ( this.checks.has( "figs" ) && !row.figs ) return false;
      if ( this.checks.has( "curated" ) && !row.curated ) return false;
      if ( this.checks.has( "code" ) && !row.code_n ) return false;
    } else {
      const from = Dom.get( "review-pool-from" ).value;
      if ( from === "refs" && !row.lib_cites ) return false;
      if ( from === "citing" && !row.cites_lib ) return false;
      if ( from === "both" && !( row.lib_cites && row.cites_lib ) ) return false;
      if ( this.checks.has( "cited2" ) && ( row.lib_cites || 0 ) < 2 ) return false;
      if ( this.checks.has( "data" ) && !( row.datasets || [] ).length ) return false;
      if ( this.checks.has( "oa" ) && !row.oa_pdf ) return false;
    }
    const text = Dom.get( "review-search" ).value.trim().toLowerCase();
    if ( !text ) return true;
    const hay = [ row.title , row.doi , row.model_name , row.task , ( row.datasets || [] ).join( " " ) , ( row.authors || [] ).join( " " ) ,
      row.journal ].join( " " ).toLowerCase();
    return text.split( /\s+/ ).every( ( word ) => hay.includes( word ) );
  },

  // [value, missing]: a paper without the sort key always goes last,
  // whichever way the sort runs.
  sortKey( row , by ) {
    switch ( by ) {
      case "added": return row.added || null;
      case "pubdate": return row.pubdate || ( row.year ? String( row.year ) : null );
      case "year": return row.year || null;
      case "cites": return this.pool === "missing" ? row.cited_by : row.cites;
      case "title": return ( row.title || "" ).toLowerCase() || null;
      case "model": return ( row.model_name || "" ).toLowerCase() || null;
      default: return null;
    }
  },

  sorted( rows ) {
    const by = Dom.get( "review-sort" ).value;
    const flip = Dom.get( "review-reverse" ).getAttribute( "aria-pressed" ) === "true" ? -1 : 1;
    const cmp = ( a , b ) => ( a < b ? -1 : a > b ? 1 : 0 );
    const newest = ( row ) => row.added || row.pubdate || String( row.year || "" );
    const out = rows.slice();
    if ( !by || by === "priority" ) {
      if ( this.pool === "missing" && !by ) {
        // As the server sent them: connections, then citations, then newest.
        return flip < 0 ? out.reverse() : out;
      }
      out.sort( ( a , b ) => flip * ( cmp( a.priority == null ? 99 : a.priority , b.priority == null ? 99 : b.priority ) || -cmp( newest( a ) , newest( b ) ) ) );
      return out;
    }
    // Text sorts run A to Z, the rest biggest or newest first; Reverse flips.
    const ascending = by === "title" || by === "model";
    out.sort( ( a , b ) => {
      const x = this.sortKey( a , by );
      const y = this.sortKey( b , by );
      if ( x == null || y == null ) return x == null && y == null ? 0 : x == null ? 1 : -1;
      return flip * ( ascending ? cmp( x , y ) : -cmp( x , y ) );
    } );
    return out;
  },

  draw( reset ) {
    if ( reset ) this.limit = this.PAGE;
    this.paintFilter();
    const all = this.rows();
    this.shown = this.sorted( all.filter( ( row ) => this.matches( row ) ) );
    const list = Dom.get( "review-list" );
    Dom.clear( list );
    this.shown.slice( 0 , this.limit ).forEach( ( row ) => list.appendChild( this.card( row ) ) );
    const empty = Dom.get( "review-empty" );
    Dom.text( empty , I18n.get( all.length ? "review.empty" : this.pool === "missing" ? "review.empty_missing" : "review.empty_library" ) );
    Dom.show( empty , this.shown.length === 0 && this.loaded[ this.pool ] );
    const more = Dom.get( "review-more" );
    const left = this.shown.length - this.limit;
    Dom.text( more , I18n.get( "review.more" ).replace( "{n}" , Math.min( left , this.PAGE ).toLocaleString() ) );
    Dom.show( more , left > 0 );
    Dom.text( Dom.get( "review-count" ) , I18n.get( "review.count" ).replace( "{n}" , this.shown.length.toLocaleString() ).replace( "{total}" , all.length.toLocaleString() ) );
    Nav.summary( "review" , Dom.get( "review-count" ).textContent );
  },

  // -- a card --------------------------------------------------------------------------

  id( row ) {
    return this.pool === "missing" ? row.wid : row.key;
  },

  taskName( priority ) {
    const tasks = ( this.data.library || {} ).tasks || this.tasks || [];
    return tasks.filter( ( t ) => t.priority === priority ).map( ( t ) => t.name ).join( ", " ) || "unclassified";
  },

  card( row ) {
    const id = this.id( row );
    const missing = this.pool === "missing";
    const head = [];
    if ( row.priority != null ) {
      head.push( this.pill( I18n.get( "review.priority_badge" ).replace( "{n}" , row.priority ) , row.priority <= 2 ? "text-bg-primary" : "text-bg-light border" ,
        I18n.get( "review.priority_title" ).replace( "{n}" , row.priority ).replace( "{task}" , () => this.taskName( row.priority ) ) ) );
    }
    const title = missing
      ? Dom.el( "a" , { class: "paper-title fw-semibold" , text: row.title || row.wid , attrs: { href: row.doi ? "https://doi.org/" + row.doi : "https://openalex.org/" + row.wid , target: "_blank" , rel: "noopener" } } )
      : Content.titleLink( row , { keys: this.shown.map( ( r ) => r.key ) } );
    title.classList.add( "fw-semibold" );
    head.push( title );
    if ( row.state === "borderline" ) head.push( this.pill( I18n.get( "review.borderline" ) , "text-bg-warning" , I18n.get( "review.borderline_title" ) ) );
    if ( row.curated ) head.push( this.pill( I18n.get( "review.curated" ) , "text-bg-info" , I18n.get( "review.curated_title" ) ) );
    if ( row.current === false ) head.push( this.pill( I18n.get( "review.stale" ) , "text-bg-light border" , I18n.get( "review.stale_title" ) ) );

    const facts = [];
    const meta = PaperLinks.meta( row , row.n_authors );
    if ( meta ) facts.push( meta );
    if ( missing ) {
      facts.push( I18n.get( "review.conn" ).replace( "{n}" , row.conn ) );
    } else if ( row.added ) {
      facts.push( I18n.get( "review.added" ).replace( "{date}" , row.added.slice( 0 , 10 ) ) );
    }
    const cites = missing ? row.cited_by : row.cites;
    if ( cites != null ) facts.push( Number( cites ) === 1 ? I18n.get( "review.cites_one" ) : I18n.get( "review.cites" ).replace( "{n}" , Number( cites ).toLocaleString() ) );
    const factLine = Dom.el( "div" , { class: "small text-body-secondary" , text: facts.join( " · " ) } );
    if ( missing ) factLine.title = I18n.get( "review.conn_title" ).replace( "{refs}" , row.lib_cites ).replace( "{citing}" , row.cites_lib );

    const tags = [];
    const tag = ( label , value ) => {
      if ( value ) tags.push( Dom.el( "span" , { class: "me-3" , children: [ Dom.el( "span" , { class: "text-body-secondary" , text: I18n.get( label ) + " " } ) , Dom.el( "span" , { text: value } ) ] } ) );
    };
    tag( "review.model" , row.model_name );
    tag( "review.task" , row.task );
    tag( "review.datasets" , ( row.datasets || [] ).join( ", " ) );
    if ( row.near_miss ) tag( "review.col_missing" , row.miss_label || row.near_miss );

    const links = [];
    if ( missing ) {
      if ( row.doi ) links.push( PaperLinks.link( "https://doi.org/" + row.doi , "links.doi" , "links.doi_title" ) );
      if ( row.oa_pdf ) links.push( Dom.el( "a" , { class: "paper-link" , text: I18n.get( "review.oa_pdf" ) , attrs: { href: row.oa_pdf , target: "_blank" , rel: "noopener" } } ) );
      links.push( Dom.el( "a" , { class: "paper-link" , text: I18n.get( "review.openalex" ) , attrs: { href: "https://openalex.org/" + row.wid , target: "_blank" , rel: "noopener" } } ) );
    } else {
      links.push( PaperLinks.strip( row ) );
      if ( row.figures_n ) {
        links.push( Dom.el( "a" , { class: "paper-link" , text: I18n.get( "review.figures" ) ,
          attrs: { href: "/api/figures/image?key=" + encodeURIComponent( row.key ) + "&n=0" , target: "_blank" , rel: "noopener" , title: I18n.get( "review.figures_title" ) } } ) );
      }
    }
    const holder = Dom.el( "div" , { class: "review-details mt-2" } );
    const toggle = Dom.el( "button" , { class: "btn btn-link btn-sm p-0 ms-auto" , attrs: { type: "button" , "aria-expanded": "false" } ,
      text: I18n.get( "review.details" ) } );
    const show = async ( on ) => {
      toggle.setAttribute( "aria-expanded" , on ? "true" : "false" );
      Dom.text( toggle , I18n.get( on ? "review.hide_details" : "review.details" ) );
      Dom.show( holder , on );
      if ( on ) this.open.add( id );
      else this.open.delete( id );
      if ( on ) await this.fillDetails( holder , row );
    };
    toggle.addEventListener( "click" , () => show( toggle.getAttribute( "aria-expanded" ) !== "true" ) );
    Dom.show( holder , false );
    const card = Dom.el( "div" , { class: "list-group-item py-3" + ( row.state === "borderline" ? " review-borderline" : "" ) , attrs: { "data-review-id": id } , children: [
      Dom.el( "div" , { class: "d-flex flex-wrap align-items-center gap-2" , children: head } ),
      factLine,
      tags.length ? Dom.el( "div" , { class: "small mt-1" , children: tags } ) : Dom.el( "span" ),
      Dom.el( "div" , { class: "d-flex flex-wrap align-items-center gap-2 small mt-1" , children: [ Dom.el( "span" , { class: "paper-links" , children: links } ) , toggle ] } ),
      holder,
    ] } );
    if ( this.open.has( id ) ) show( true );
    return card;
  },

  async fillDetails( holder , row ) {
    const id = this.id( row );
    let review = this.details.get( this.pool + ":" + id );
    if ( !review ) {
      Dom.clear( holder );
      holder.appendChild( Dom.el( "p" , { class: "small text-body-secondary mb-0" , text: I18n.get( "review.loading" ) } ) );
      try {
        const answer = this.pool === "missing"
          ? await Api.request( "/api/review/missing/work" + Api.query( { wid: row.wid } ) )
          : await Api.request( "/api/review/paper" + Api.query( { key: row.key } ) );
        review = answer.review;
      } catch ( error ) {
        Dom.clear( holder );
        holder.appendChild( Dom.el( "p" , { class: "small text-danger mb-0" , text: error.message } ) );
        return;
      }
      this.details.set( this.pool + ":" + id , review );
    }
    Dom.clear( holder );
    holder.appendChild( this.detailsBody( review ) );
  },

  detailsBody( review ) {
    const body = Dom.el( "div" , { class: "small" } );
    if ( this.pool === "missing" ) {
      body.appendChild( Dom.el( "p" , { class: "text-body-secondary fst-italic mb-2" , text: I18n.get( "review.abstract_only" ) } ) );
    }
    const why = ( review.verdict || {} ).why || [];
    if ( why.length ) {
      body.appendChild( Dom.el( "div" , { class: "fw-semibold" , text: I18n.get( "review.why" ) } ) );
      body.appendChild( Dom.el( "ul" , { class: "list-unstyled mb-2" , children: why.map( ( test ) => Dom.el( "li" , { children: [
        Dom.el( "span" , { class: "badge me-1 " + ( test.pass ? "text-bg-success" : "text-bg-secondary" ) , text: I18n.get( test.pass ? "review.pass" : "review.fail" ) } ),
        Dom.el( "span" , { class: "fw-semibold" , text: test.test + ": " } ),
        Dom.el( "span" , { text: test.detail } ),
      ] } ) ) } ) );
    }
    const groups = new Map();
    Object.entries( review.fields || {} ).forEach( ( [ name , field ] ) => {
      if ( !groups.has( field.group ) ) groups.set( field.group , [] );
      groups.get( field.group ).push( [ name , field ] );
    } );
    const row = Dom.el( "div" , { class: "row g-3" } );
    groups.forEach( ( fields , group ) => {
      const stated = this.pool === "missing" ? fields.filter( ( [ , f ] ) => f.value || f.note ) : fields;
      const list = Dom.el( "dl" , { class: "mb-0" } );
      stated.forEach( ( [ name , field ] ) => list.appendChild( Dom.el( "div" , { class: "row g-1 mb-1" , children: [
        Dom.el( "dt" , { class: "col-12 col-sm-5 text-body-secondary fw-normal" , text: name.replace( /_/g , " " ) } ),
        Dom.el( "dd" , { class: "col-12 col-sm-7 mb-0" , children: [ this.value( field ) ] } ),
      ] } ) ) );
      if ( !stated.length ) list.appendChild( Dom.el( "div" , { class: "text-body-secondary" , text: I18n.get( "review.groups_none" ) } ) );
      row.appendChild( Dom.el( "div" , { class: "col-12 col-md-6 col-xl-4" , children: [
        Dom.el( "div" , { class: "fw-semibold border-bottom mb-1" , text: group } ), list,
      ] } ) );
    } );
    body.appendChild( row );
    if ( this.pool === "missing" && review.abstract ) {
      body.appendChild( Dom.el( "details" , { class: "mt-2" , children: [
        Dom.el( "summary" , { text: I18n.get( "review.abstract" ) } ),
        Dom.el( "p" , { class: "mb-0 mt-1" , text: review.abstract } ),
      ] } ) );
    }
    return body;
  },

  // One value: click it for its quote and the other values stated.
  value( field ) {
    if ( !field.value ) {
      const text = field.note ? I18n.get( "review.several_datasets" ) : I18n.get( "review.not_stated" );
      return Dom.el( "span" , { class: "text-body-secondary fst-italic" , text: text , attrs: field.note ? { title: field.note } : {} } );
    }
    const wrap = Dom.el( "span" );
    const button = Dom.el( "button" , { class: "btn btn-link btn-sm p-0 text-start review-value" , attrs: { type: "button" , "aria-expanded": "false" } , text: field.value } );
    wrap.appendChild( button );
    if ( field.source === "dataset" ) {
      wrap.appendChild( Dom.el( "span" , { class: "badge text-bg-light border ms-1" ,
        text: I18n.get( "review.from_dataset" ).replace( "{dataset}" , () => field.from_dataset ).replace( "{n}" , field.dataset_papers ) ,
        attrs: { title: I18n.get( "review.from_dataset_title" ).replace( "{dataset}" , () => field.from_dataset ).replace( "{n}" , field.dataset_papers ) } } ) );
    }
    if ( field.source === "curated" ) wrap.appendChild( Dom.el( "span" , { class: "badge text-bg-info ms-1" , text: I18n.get( "review.curated" ) } ) );
    const alts = ( field.values || [] ).length - 1;
    if ( alts > 0 ) wrap.appendChild( Dom.el( "span" , { class: "text-body-secondary ms-1" , text: I18n.get( "review.alts" ).replace( "{n}" , alts ) , attrs: { title: I18n.get( "review.alts_title" ) } } ) );
    const quote = Dom.el( "div" , { class: "review-evidence border-start ps-2 my-1" } );
    Dom.show( quote , false );
    button.addEventListener( "click" , () => {
      const on = button.getAttribute( "aria-expanded" ) !== "true";
      button.setAttribute( "aria-expanded" , on ? "true" : "false" );
      if ( on && !quote.childNodes.length ) {
        const evidence = field.evidence || [];
        if ( evidence.length ) evidence.forEach( ( text ) => quote.appendChild( Dom.el( "blockquote" , { class: "mb-1 fst-italic" , text: "“" + text + "”" } ) ) );
        else if ( field.source !== "dataset" ) quote.appendChild( Dom.el( "div" , { class: "text-body-secondary" , text: I18n.get( "review.evidence_none" ) } ) );
        if ( ( field.values || [] ).length > 1 ) {
          const counts = field.counts || {};
          quote.appendChild( Dom.el( "div" , { class: "text-body-secondary" , text: I18n.get( "review.values_seen" ) + ": " +
            field.values.map( ( v ) => v + ( counts[ v ] ? " ×" + counts[ v ] : "" ) ).join( ", " ) } ) );
        }
      }
      Dom.show( quote , on );
    } );
    wrap.appendChild( quote );
    return wrap;
  },

  // -- the tables at the bottom ------------------------------------------------------------

  table( holder , columns , rows ) {
    Dom.clear( holder );
    holder.appendChild( Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: columns.map( ( c ) => Dom.el( "th" , { class: c.end ? "text-end" : "" , text: I18n.get( c.label ) , attrs: { scope: "col" } } ) ) } ) ] } ) );
    holder.appendChild( Dom.el( "tbody" , { children: rows.map( ( row ) => Dom.el( "tr" , { children: columns.map( ( c ) => {
      const value = c.cell( row );
      return Dom.el( "td" , { class: ( c.end ? "text-end " : "" ) + ( c.cls || "" ) , children: [ value instanceof Node ? value : document.createTextNode( value == null ? "" : String( value ) ) ] } );
    } ) } ) ) } ) );
  },

  paintBottom( data ) {
    const missing = this.pool === "missing";
    const excluded = missing ? [] : data.papers.filter( ( row ) => row.state === "excluded" );
    Dom.show( Dom.get( "review-excluded-card" ) , !missing && excluded.length > 0 );
    if ( !missing ) {
      Dom.text( Dom.get( "review-excluded-title" ) , I18n.get( "review.excluded_title" ).replace( "{n}" , excluded.length.toLocaleString() ) );
      const failed = ( row ) => ( row.why || [] ).filter( ( t ) => !t.pass ).map( ( t ) => t.test + " (" + t.detail + ")" ).join( "; " );
      excluded.sort( ( a , b ) => ( a.reason_code || "" ).localeCompare( b.reason_code || "" ) || ( b.added || "" ).localeCompare( a.added || "" ) );
      this.table( Dom.get( "review-excluded" ) , [
        { label: "review.col_paper" , cell: ( row ) => Content.titleLink( row ) },
        { label: "review.col_year" , end: true , cell: ( row ) => row.year || "" },
        { label: "review.col_reason" , cls: "small" , cell: ( row ) => row.reason || row.reason_code },
        { label: "review.col_why" , cls: "small text-body-secondary" , cell: failed },
      ] , excluded );
    }
    const near = missing ? data.near_misses || [] : [];
    Dom.show( Dom.get( "review-near-card" ) , missing && near.length > 0 );
    if ( missing ) {
      Dom.text( Dom.get( "review-near-title" ) , I18n.get( "review.near_title" ).replace( "{n}" , ( data.counts.near_misses || 0 ).toLocaleString() ) );
      this.table( Dom.get( "review-near" ) , [
        { label: "review.col_paper" , cell: ( row ) => Dom.el( "a" , { text: row.title || row.wid , attrs: { href: row.doi ? "https://doi.org/" + row.doi : "https://openalex.org/" + row.wid , target: "_blank" , rel: "noopener" } } ) },
        { label: "review.col_year" , end: true , cell: ( row ) => row.year || "" },
        { label: "review.col_conn" , end: true , cell: ( row ) => row.conn },
        { label: "review.col_cites" , end: true , cell: ( row ) => ( row.cited_by || 0 ).toLocaleString() },
        { label: "review.col_missing" , cls: "small" , cell: ( row ) => row.miss_label || row.near_miss },
        { label: "review.col_task" , cls: "small text-body-secondary" , cell: ( row ) => row.task },
      ] , near );
      const reasons = Object.entries( data.reasons || {} );
      const names = ( this.data.library || {} ).reasons || {};
      Dom.show( Dom.get( "review-tally-card" ) , reasons.length > 0 );
      this.table( Dom.get( "review-tally" ) , [
        { label: "review.col_reason" , cell: ( [ code ] ) => names[ code ] || code },
        { label: "review.col_count" , end: true , cell: ( [ , n ] ) => n.toLocaleString() },
      ] , reasons );
    } else {
      Dom.show( Dom.get( "review-tally-card" ) , false );
    }
    const consensus = missing ? [] : data.consensus || [];
    Dom.show( Dom.get( "review-consensus-card" ) , consensus.length > 0 );
    this.table( Dom.get( "review-consensus" ) , [
      { label: "review.col_dataset" , cell: ( row ) => row.dataset },
      { label: "review.col_parameter" , cell: ( row ) => row.parameter.replace( /_/g , " " ) },
      { label: "review.col_value" , cls: "fw-semibold" , cell: ( row ) => row.value },
      { label: "review.col_papers" , end: true , cell: ( row ) => row.n },
      { label: "review.col_others" , cls: "small text-body-secondary" , cell: ( row ) => ( row.others || [] ).map( ( o ) => o.value + " (" + o.n + ")" ).join( ", " ) },
    ] , consensus );
  },

  // -- export: the cards shown, in their order ------------------------------------------------

  exportRows() {
    const missing = this.pool === "missing";
    return this.shown.map( ( row ) => {
      const out = missing
        ? { wid: row.wid , doi: row.doi , title: row.title , year: row.year , pubdate: row.pubdate , authors: row.authors , cited_by: row.cited_by ,
          lib_cites: row.lib_cites , cites_lib: row.cites_lib , oa_pdf: row.oa_pdf }
        : { key: row.key , doi: row.doi , title: row.title , year: row.year , pubdate: row.pubdate , added: row.added , cites: row.cites ,
          state: row.state , curated: row.curated , lists: ( row.lists || [] ).map( ( l ) => l.name + " #" + l.position ) , figs: row.figs , code_n: row.code_n };
      Object.assign( out , { priority: row.priority , task: row.task , model_name: row.model_name , datasets: row.datasets || [] , attention_role: row.attention_role || "" } );
      if ( !missing ) {
        out.fields = {};
        Object.entries( row.fields || {} ).forEach( ( [ name , f ] ) => {
          out.fields[ name ] = f.value ? { value: f.value , source: f.source , from_dataset: f.from_dataset || undefined } : null;
        } );
      }
      return out;
    } );
  },

  exportJson() {
    const name = this.pool === "missing" ? "review-missing" : "review";
    Dom.download( name + ".json" , JSON.stringify( this.exportRows() , null , 1 ) );
  },

  exportCsv() {
    const rows = this.exportRows();
    const fieldNames = this.pool === "missing" ? [] : ( this.data.library.fields || [] ).map( ( f ) => f.name );
    const base = rows.length ? Object.keys( rows[ 0 ] ).filter( ( k ) => k !== "fields" ) : [];
    const columns = base.concat( fieldNames );
    const sheet = {
      name: I18n.get( "review.sheet_name" ),
      columns: columns,
      rows: rows.map( ( row ) => base.map( ( k ) => Array.isArray( row[ k ] ) ? row[ k ].join( "; " ) : row[ k ] )
        .concat( fieldNames.map( ( name ) => {
          const f = ( row.fields || {} )[ name ];
          return f ? f.value + ( f.source === "dataset" ? " (from " + f.from_dataset + ")" : "" ) : "";
        } ) ) ),
    };
    ExportTable.csv( this.pool === "missing" ? "review-missing" : "review" , sheet );
  },
};
