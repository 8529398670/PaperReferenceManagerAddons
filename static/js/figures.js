// The Figures screen: every figure cropped from the library's PDFs, paper by
// paper -- or, in the Method figures view, only those whose caption reads as a
// model design -- to pick from. The old /images and /method-images reports as
// one live screen.
//
// Click a figure to pick it (again to take it back); picks keep their order.
// Skip a paper you are done with (Space skips the current one, the arrow keys
// step between papers). Each view has its own picks and skips; a figure
// picked in the other view says so, and a chip shows just those.
//
// There can be ~17k crops, so papers come a page at a time as the grid
// scrolls, and an image is only loaded while it is near the screen (and let
// go again when it is far away), so the page stays light however far down.
const FiguresView = {
  view: "all",
  chip: "all",
  sort: "added",
  dir: "desc",
  mod: "",
  term: "",
  offset: 0,
  pageSize: 30,
  ticket: 0,
  loading: false,
  done: false,
  papers: [],
  current: -1,
  answer: null,
  state: null,

  init() {
    this.panel = Dom.get( "figures-panel" );
    Dom.show( this.panel , true );
    this.grid = Dom.get( "figures-grid" );
    Dom.all( "[data-figures-view]" ).forEach( ( tab ) => tab.addEventListener( "click" , ( event ) => {
      event.preventDefault();
      this.setView( tab.getAttribute( "data-figures-view" ) );
    } ) );
    Dom.typed( Dom.get( "figures-search" ) , () => this.reload() , 300 );
    Dom.get( "figures-mod" ).addEventListener( "change" , ( event ) => { this.mod = event.target.value; this.reload(); } );
    Dom.get( "figures-term" ).addEventListener( "change" , ( event ) => { this.term = event.target.value; this.reload(); } );
    Dom.get( "figures-sort" ).addEventListener( "change" , ( event ) => { this.sort = event.target.value; this.remember(); this.reload(); } );
    Dom.onPress( Dom.get( "figures-dir" ) , () => {
      this.dir = this.dir === "desc" ? "asc" : "desc";
      this.remember();
      this.paintDir();
      this.reload();
    } );
    Dom.onPress( Dom.get( "figures-clear" ) , () => this.clear() );
    this.paintFilter = DataTable.filters( Dom.get( "figures-filter" ) ,
      () => ( this.mod ? 1 : 0 ) + ( this.term ? 1 : 0 ),
      () => {
        this.mod = "";
        this.term = "";
        this.reload();
      } );
    this.recall();
    this.paintDir();
    // Images load only near the screen and are let go far from it.
    this.images = new IntersectionObserver( ( entries ) => entries.forEach( ( entry ) => {
      const img = entry.target;
      if ( entry.isIntersecting ) {
        if ( !img.getAttribute( "src" ) ) img.setAttribute( "src" , img.getAttribute( "data-src" ) );
      } else if ( img.getAttribute( "src" ) && !this.near( img ) ) {
        img.removeAttribute( "src" );
      }
    } ) , { root: this.scroller() , rootMargin: "1200px 0px" } );
    this.sentinel = Dom.el( "div" , { class: "figures-sentinel" } );
    this.more = new IntersectionObserver( ( entries ) => {
      if ( entries.some( ( entry ) => entry.isIntersecting ) ) this.load( true );
    } , { root: this.scroller() , rootMargin: "1500px 0px" } );
    document.addEventListener( "keydown" , ( event ) => this.onKey( event ) );
    // A paper's figures cropped by the worker while the screen is open.
    const soon = Content.throttle( () => {
      if ( Nav.current() === "figures" ) this.reload( true );
      else this.stale = true;
    } , 20000 );
    Content.on( "paper" , ( data ) => {
      if ( data.stage === "figures" && data.state === "done" ) soon();
    } );
    window.addEventListener( "hashchange" , () => {
      if ( Nav.current() === "figures" && ( this.stale || !this.answer ) ) this.reload();
    } );
    if ( Nav.current() === "figures" ) this.reload();
  },

  // From md up the grid scrolls inside the screen; on a phone the page does.
  scroller() {
    return window.matchMedia( "(min-width: 768px)" ).matches ? this.grid : null;
  },

  near( img ) {
    const box = img.getBoundingClientRect();
    const root = this.scroller();
    const area = root ? root.getBoundingClientRect() : { top: 0 , bottom: window.innerHeight };
    return box.bottom > area.top - 2400 && box.top < area.bottom + 2400;
  },

  recall() {
    try {
      const saved = JSON.parse( window.localStorage.getItem( "figures.prefs" ) || "{}" ) || {};
      if ( saved.sort ) this.sort = saved.sort;
      if ( saved.dir ) this.dir = saved.dir;
      if ( saved.view ) this.view = saved.view;
    } catch ( error ) { /* only a convenience */ }
    Dom.get( "figures-sort" ).value = this.sort;
    this.paintTabs();
  },

  remember() {
    try {
      window.localStorage.setItem( "figures.prefs" , JSON.stringify( { sort: this.sort , dir: this.dir , view: this.view } ) );
    } catch ( error ) { /* only a convenience */ }
  },

  paintDir() {
    const button = Dom.get( "figures-dir" );
    const label = I18n.get( this.dir === "desc" ? "figures.dir_desc" : "figures.dir_asc" );
    button.setAttribute( "title" , label );
    button.setAttribute( "aria-label" , label );
    button.querySelector( "i" ).className = "bi " + ( this.dir === "desc" ? "bi-sort-down" : "bi-sort-up" );
  },

  paintTabs() {
    Dom.all( "[data-figures-view]" ).forEach( ( tab ) => {
      const on = tab.getAttribute( "data-figures-view" ) === this.view;
      tab.classList.toggle( "active" , on );
      if ( on ) tab.setAttribute( "aria-current" , "true" );
      else tab.removeAttribute( "aria-current" );
    } );
    Dom.show( Dom.get( "figures-term-group" ) , this.view === "method" );
    Dom.get( "figures-export-json" ).setAttribute( "href" , "/api/figures/export?view=" + this.view + "&format=json" );
    Dom.get( "figures-export-csv" ).setAttribute( "href" , "/api/figures/export?view=" + this.view + "&format=csv" );
  },

  setView( view ) {
    if ( view === this.view ) return;
    this.view = view;
    this.chip = "all";
    this.term = "";
    this.remember();
    this.paintTabs();
    this.reload();
  },

  params( offset ) {
    const params = new URLSearchParams( {
      view: this.view , sort: this.sort , dir: this.dir , chip: this.chip , limit: String( this.pageSize ) , offset: String( offset ),
    } );
    const text = Dom.get( "figures-search" ).value.trim();
    if ( text ) params.set( "q" , text );
    if ( this.mod ) params.set( "mod" , this.mod );
    if ( this.term && this.view === "method" ) params.set( "term" , this.term );
    return params;
  },

  // keep: the same papers again (a figure cropped elsewhere), keeping the
  // place in the grid rather than jumping to the top.
  async reload( keep ) {
    this.stale = false;
    const shown = keep ? Math.max( this.papers.length , this.pageSize ) : this.pageSize;
    await this.load( false , shown );
  },

  async load( more , size ) {
    if ( more && ( this.loading || this.done ) ) return;
    const ticket = ++this.ticket;
    this.loading = true;
    const offset = more ? this.offset : 0;
    const params = this.params( offset );
    if ( size ) params.set( "limit" , String( Math.min( size , 200 ) ) );
    let answer;
    try {
      // The view's picks too, in pick order, for each pick's number.
      if ( !more || !this.state ) this.state = await Api.request( "/api/figures/state?view=" + this.view );
      answer = await Api.request( "/api/figures?" + params );
    } catch ( error ) {
      if ( ticket === this.ticket ) {
        this.loading = false;
        Dom.toast( error.message , "error" );
      }
      return;
    }
    if ( ticket !== this.ticket ) return;
    this.loading = false;
    this.answer = answer;
    if ( !more ) {
      this.papers = [];
      this.current = -1;
      this.more.disconnect();
      this.grid.querySelectorAll( "img[data-src]" ).forEach( ( img ) => this.images.unobserve( img ) );
      Dom.clear( this.grid );
    }
    answer.papers.forEach( ( paper ) => {
      this.papers.push( paper );
      this.grid.appendChild( this.drawPaper( paper , this.papers.length - 1 ) );
    } );
    this.offset = answer.next == null ? offset + answer.papers.length : answer.next;
    this.done = answer.next == null;
    this.sentinel.remove();
    if ( !this.done ) {
      this.grid.appendChild( this.sentinel );
      this.more.observe( this.sentinel );
    }
    if ( !this.papers.length ) {
      this.grid.appendChild( Dom.el( "p" , { class: "text-body-secondary p-3 mb-0" , text: I18n.get( "figures.empty" ) } ) );
    }
    this.drawChrome( answer );
  },

  drawChrome( answer ) {
    Dom.text( Dom.get( "figures-count" ) , I18n.get( "figures.count" )
      .replace( "{papers}" , answer.total.toLocaleString() )
      .replace( "{figures}" , answer.figures.toLocaleString() )
      .replace( "{picks}" , answer.picks.toLocaleString() ) );
    Nav.summary( "figures" , Dom.get( "figures-count" ).textContent );
    this.drawChips( answer );
    this.drawSelect( Dom.get( "figures-mod" ) , answer.mods , this.mod );
    this.drawSelect( Dom.get( "figures-term" ) , answer.terms , this.term );
    this.paintFilter();
    const note = Dom.get( "figures-note" );
    const none = !answer.total && this.chip === "all" && !this.mod && !this.term && !Dom.get( "figures-search" ).value.trim();
    let text = "";
    if ( none && this.view === "all" ) text = I18n.get( "figures.no_figures" );
    else if ( !answer.workers ) text = I18n.get( "figures.no_worker" );
    Dom.text( note , text );
    Dom.show( note , Boolean( text ) );
    note.classList.toggle( "alert-warning" , none );
    note.classList.toggle( "alert-info" , !none );
  },

  drawSelect( select , items , value ) {
    Dom.clear( select );
    select.appendChild( Dom.el( "option" , { text: I18n.get( "figures.any" ) , attrs: { value: "" } } ) );
    const names = items.map( ( item ) => item.name );
    if ( value && !names.includes( value ) ) items = items.concat( [ { name: value , n: 0 } ] );
    items.forEach( ( item ) => select.appendChild( Dom.el( "option" , { text: item.name + " (" + item.n + ")" , attrs: { value: item.name } } ) ) );
    select.value = value;
  },

  drawChips( answer ) {
    const holder = Dom.get( "figures-chips" );
    Dom.clear( holder );
    const counts = answer.counts || {};
    const chips = [ "all" , "selected" , "other" , "skipped" ];
    if ( this.view === "method" ) chips.splice( 1 , 0 , "lead" );
    chips.forEach( ( chip ) => {
      const on = chip === this.chip;
      const button = Dom.el( "button" , {
        class: "btn btn-sm " + ( on ? "btn-primary" : "btn-outline-secondary" ),
        attrs: { type: "button" , "aria-pressed": String( on ) , title: chip === "lead" ? I18n.get( "figures.chip_lead_title" ) : "" },
        children: [ Dom.el( "span" , { text: I18n.get( "figures.chip_" + chip ) + " " } ) , Dom.el( "span" , { class: "badge text-bg-light border" , text: String( counts[ chip ] || 0 ) } ) ],
        on: { click: () => {
          this.chip = on && chip !== "all" ? "all" : chip;
          this.reload();
        } },
      } );
      holder.appendChild( button );
    } );
    // The keywords matched most, as chips too; the rest are in the Filter menu.
    if ( this.view === "method" && answer.terms.length ) {
      // On a phone the keywords stay in the Filter menu.
      holder.appendChild( Dom.el( "span" , { class: "vr mx-1 d-none d-md-inline-block" } ) );
      answer.terms.slice( 0 , 8 ).forEach( ( item ) => {
        const on = item.name === this.term;
        holder.appendChild( Dom.el( "button" , {
          class: "btn btn-sm d-none d-md-inline-block " + ( on ? "btn-secondary" : "btn-outline-secondary" ),
          attrs: { type: "button" , "aria-pressed": String( on ) },
          text: item.name + " " + item.n,
          on: { click: () => { this.term = on ? "" : item.name; this.reload(); } },
        } ) );
      } );
      if ( answer.terms.length > 8 ) {
        holder.appendChild( Dom.el( "span" , { class: "small text-body-secondary align-self-center d-none d-md-inline" , text: I18n.get( "figures.more_terms" ).replace( "{n}" , answer.terms.length - 8 ) } ) );
      }
    }
  },

  // -- one paper ------------------------------------------------------------

  drawPaper( paper , index ) {
    const skip = Dom.el( "button" , {
      class: "btn btn-sm " + ( paper.skipped ? "btn-outline-primary" : "btn-outline-secondary" ),
      attrs: { type: "button" , title: I18n.get( "figures.skip_title" ) },
      children: [ Dom.el( "i" , { class: "bi " + ( paper.skipped ? "bi-arrow-counterclockwise" : "bi-eye-slash" ) , attrs: { "aria-hidden": "true" } } ) ,
        Dom.el( "span" , { text: " " + I18n.get( paper.skipped ? "figures.unskip" : "figures.skip" ) } ) ],
      on: { click: () => this.skip( index ) },
    } );
    const meta = [ paper.year , ( paper.mods || [] ).join( ", " ) ].filter( Boolean ).join( " · " );
    const head = Dom.el( "div" , { class: "d-flex flex-wrap align-items-baseline gap-2 mb-2" , children: [
      Dom.el( "h3" , { class: "h6 mb-0 me-auto figures-paper-title" , children: [ Content.titleLink( paper ) ] } ),
      meta ? Dom.el( "span" , { class: "small text-body-secondary" , text: meta } ) : null,
      skip,
    ].filter( Boolean ) } );
    const row = Dom.el( "div" , { class: "row row-cols-2 row-cols-md-3 row-cols-xl-4 row-cols-xxl-6 g-2" } );
    paper.figures.forEach( ( figure ) => row.appendChild( this.drawFigure( paper , figure ) ) );
    const block = Dom.el( "section" , {
      class: "card mb-3 figures-paper" + ( paper.skipped ? " is-skipped" : "" ),
      attrs: { "data-index": String( index ) , "aria-label": paper.title || paper.key },
      children: [ Dom.el( "div" , { class: "card-body p-2 p-md-3" , children: [ head , row ] } ) ],
      on: { click: () => this.setCurrent( index , false ) },
    } );
    return block;
  },

  drawFigure( paper , figure ) {
    const src = "/api/figures/image?key=" + encodeURIComponent( paper.key ) + "&n=" + figure.n;
    const img = Dom.el( "img" , { class: "figures-img" , attrs: { "data-src": src , alt: figure.caption ? figure.caption.slice( 0 , 160 ) : "" } } );
    if ( figure.w && figure.h ) img.style.aspectRatio = figure.w + " / " + figure.h;
    this.images.observe( img );
    const badges = [];
    const order = this.pickOrder( figure.id );
    if ( figure.picked ) badges.push( Dom.badge( I18n.get( "figures.picked" ).replace( "{n}" , order ) , "text-bg-primary" ) );
    if ( figure.picked_other ) badges.push( Dom.badge( I18n.get( "figures.picked_other" ) , "text-bg-light border" ) );
    const button = Dom.el( "button" , {
      class: "figures-pick btn p-0 text-start w-100",
      attrs: { type: "button" , "aria-pressed": String( Boolean( figure.picked ) ) , title: I18n.get( "figures.pick_title" ) },
      children: [ img ],
      on: { click: ( event ) => { event.stopPropagation(); this.pick( paper , figure , button ); } },
    } );
    const caption = Dom.el( "p" , { class: "figures-caption small mb-0" , children: this.highlight( figure.caption || "" , ( figure.match || {} ).spans || [] ) } );
    const foot = Dom.el( "div" , { class: "d-flex flex-wrap align-items-center gap-1 small text-body-secondary mt-1" , children: [
      Dom.el( "span" , { text: I18n.get( "figures.figure_label" ).replace( "{n}" , figure.n ).replace( "{page}" , figure.page || "?" ) } ),
      ...badges,
      Dom.el( "a" , {
        class: "ms-auto", attrs: { href: src + "&size=full" , target: "_blank" , rel: "noopener" , title: I18n.get( "figures.open_full" ) , "aria-label": I18n.get( "figures.open_full" ) },
        children: [ Dom.el( "i" , { class: "bi bi-box-arrow-up-right" , attrs: { "aria-hidden": "true" } } ) ],
      } ),
    ] } );
    return Dom.el( "div" , { class: "col" , children: [ Dom.el( "div" , {
      class: "card h-100 figures-card" + ( figure.picked ? " is-picked" : "" ),
      children: [ Dom.el( "div" , { class: "card-body p-2" , children: [ button , foot , caption ] } ) ],
    } ) ] } );
  },

  // The caption, its matched keywords marked.
  highlight( text , spans ) {
    const out = [];
    let at = 0;
    spans.forEach( ( span ) => {
      const [ start , end ] = span;
      if ( start < at ) return;
      if ( start > at ) out.push( document.createTextNode( text.slice( at , start ) ) );
      out.push( Dom.el( "mark" , { text: text.slice( start , end ) } ) );
      at = end;
    } );
    if ( at < text.length ) out.push( document.createTextNode( text.slice( at ) ) );
    return out;
  },

  pickOrder( id ) {
    const list = this.state ? this.state.selected : [];
    const index = list.indexOf( id );
    return index >= 0 ? index + 1 : "";
  },

  // -- picking and skipping -------------------------------------------------

  async pick( paper , figure , button ) {
    const on = !figure.picked;
    const send = ( value ) => Api.post( "/api/figures/pick" , { view: this.view , ids: [ figure.id ] , pick: value } );
    try {
      this.state = await send( on );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    figure.picked = on;
    this.repaintFigure( paper , figure , button );
    Undo.record( {
      label: I18n.get( "figures.pick_title" ),
      undo: async () => { this.state = await send( !on ); figure.picked = !on; this.reload( true ); },
      redo: async () => { this.state = await send( on ); figure.picked = on; this.reload( true ); },
    } );
  },

  repaintFigure( paper , figure , button ) {
    const col = button.closest( ".col" );
    if ( col ) col.replaceWith( this.drawFigure( paper , figure ) );
  },

  async skip( index ) {
    const paper = this.papers[ index ];
    if ( !paper ) return;
    const on = !paper.skipped;
    const send = ( value ) => Api.post( "/api/figures/skip" , { view: this.view , keys: [ paper.key ] , skip: value } );
    try {
      this.state = await send( on );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    paper.skipped = on;
    const block = this.grid.querySelector( '.figures-paper[data-index="' + index + '"]' );
    if ( block ) {
      const fresh = this.drawPaper( paper , index );
      block.replaceWith( fresh );
      if ( index === this.current ) fresh.classList.add( "is-current" );
    }
    Undo.record( {
      label: I18n.get( "figures.skip_title" ),
      toast: true,
      undo: async () => { this.state = await send( !on ); this.reload( true ); },
      redo: async () => { this.state = await send( on ); this.reload( true ); },
    } );
    // Skipping walks on to the next paper, as the old report did.
    if ( on ) this.setCurrent( Math.min( index + 1 , this.papers.length - 1 ) , true );
  },

  async clear() {
    if ( !( await Dom.confirm( I18n.get( "figures.clear_confirm" ) ) ) ) return;
    const view = this.view;
    let before;
    try {
      before = await Api.request( "/api/figures/state?view=" + view );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    const set = ( state ) => Api.post( "/api/figures/replace" , { view: view , selected: state.selected , skipped: state.skipped } );
    await Undo.run( {
      label: I18n.get( "figures.cleared" ),
      toast: true,
      do: async () => { this.state = await set( { selected: [] , skipped: [] } ); await this.reload(); },
      undo: async () => { this.state = await set( before ); await this.reload(); },
    } );
  },

  // -- the keyboard ---------------------------------------------------------

  setCurrent( index , scroll ) {
    if ( index < 0 || index >= this.papers.length ) return;
    this.grid.querySelectorAll( ".figures-paper.is-current" ).forEach( ( block ) => block.classList.remove( "is-current" ) );
    this.current = index;
    const block = this.grid.querySelector( '.figures-paper[data-index="' + index + '"]' );
    if ( !block ) return;
    block.classList.add( "is-current" );
    if ( scroll ) block.scrollIntoView( { block: "start" , behavior: "smooth" } );
    if ( index >= this.papers.length - 3 ) this.load( true );
  },

  onKey( event ) {
    if ( Nav.current() !== "figures" || event.ctrlKey || event.metaKey || event.altKey ) return;
    const target = event.target;
    if ( target && ( target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test( target.tagName ) ) ) return;
    if ( document.querySelector( ".modal.show, .dropdown-menu.show" ) ) return;
    if ( event.key === "ArrowDown" || event.key === "ArrowUp" ) {
      event.preventDefault();
      this.setCurrent( Math.max( 0 , this.current + ( event.key === "ArrowDown" ? 1 : -1 ) ) , true );
    } else if ( event.key === " " && this.current >= 0 && !( target && target.tagName === "BUTTON" ) ) {
      event.preventDefault();
      this.skip( this.current );
    }
  },
};
