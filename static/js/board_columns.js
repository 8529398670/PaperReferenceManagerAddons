// The Lists board's column widths, and dragging them.
//
// The board is one CSS grid per row (the header is a row too), so the columns
// line up by every row having the same grid-template-columns. That template
// lives in ONE rule of a stylesheet made here, not in an inherited custom
// property: changing an inherited property makes the browser restyle all
// ~40,000 nodes of a long list, while changing this rule touches only the
// rows themselves. That is what keeps a drag smooth.
//
// How a drag behaves, like a spreadsheet: the edge you hold follows the
// pointer and nothing else moves. Every column has a width in pixels. Columns
// you never touched use their default; the Paper column's default is "what is
// left over" so a new board fills the screen, and the first drag of any edge
// fixes it at the width it has then, so it never gives or takes what another
// column gains. After the last column comes a filler track that takes any
// spare room, so rows stay full width without stretching a column; when the
// columns add up to more than the board, it scrolls sideways (the # and Paper
// columns stay pinned at the left).
//
// Widths are kept per browser (localStorage, the board's own "list-col-widths"
// key). Double-click an edge to put that column back to its default.
const BoardColumns = {
  MIN: 64,
  PAPER_MIN: 288,
  // In rem, as style.css has them: a column's default, the # / grip /
  // anchor cell (--board-side), the remove button, and the column gap.
  COLUMN: 16,
  SIDE: 5.75,
  END: 2.25,
  GAP: 0.75,

  lists: null,
  sheet: null,
  rule: null,
  ids: [],
  drawn: [],

  init( lists ) {
    this.lists = lists;
    try {
      this.sheet = new CSSStyleSheet();
      this.sheet.replaceSync( "@media (min-width: 768px) { #list-body .board-head, #list-body .board-rows > .board-row {} }" );
      document.adoptedStyleSheets = [ ...document.adoptedStyleSheets , this.sheet ];
      this.rule = this.sheet.cssRules[ 0 ].cssRules[ 0 ];
    } catch ( error ) {
      // No constructable stylesheets (an old browser): the custom property,
      // which style.css reads, does the same job more slowly.
      this.sheet = null;
      this.rule = null;
    }
    const board = Dom.get( "list-scroll" );
    // A wider or narrower window changes what the Paper column fills.
    new ResizeObserver( () => {
      if ( this.ids.length && !this.stored().paper ) this.apply();
    } ).observe( board );
    // A mouse wheel turned over the column labels scrolls the board
    // sideways: a plain wheel has no other way to reach the columns past the
    // window's edge (Shift+wheel and a trackpad still work anywhere).
    Dom.get( "list-head" ).addEventListener( "wheel" , ( event ) => {
      if ( event.shiftKey || event.ctrlKey || Math.abs( event.deltaX ) >= Math.abs( event.deltaY ) ) return;
      if ( board.scrollWidth <= board.clientWidth ) return;
      event.preventDefault();
      board.scrollLeft += event.deltaY;
    } , { passive: false } );
  },

  stored() {
    try {
      return JSON.parse( this.lists.local( "list-col-widths" ) || "{}" ) || {};
    } catch ( error ) {
      return {};
    }
  },

  store( widths ) {
    this.lists.local( "list-col-widths" , JSON.stringify( widths ) );
  },

  // The width each column is drawn at now: stored, else the default, the
  // Paper column filling what the others leave of the board.
  rem() {
    return parseFloat( getComputedStyle( document.documentElement ).fontSize ) || 16;
  },

  widths() {
    const rem = this.rem();
    const kept = this.stored();
    const out = {};
    let others = 0;
    this.ids.forEach( ( id ) => {
      if ( id === "paper" ) return;
      out[ id ] = kept[ id ] || Math.round( this.COLUMN * rem );
      others += out[ id ];
    } );
    if ( kept.paper ) {
      out.paper = kept.paper;
    } else {
      const board = Dom.get( "list-scroll" ).clientWidth || 1200;
      const fixed = ( this.SIDE + this.END + this.GAP * ( this.ids.length + 2 ) ) * rem + others;
      out.paper = Math.max( this.PAPER_MIN , board - fixed - 2 );
    }
    return out;
  },

  // columns: the shown columns in order (not the Paper one).
  layout( columns ) {
    this.ids = [ "paper" ].concat( columns.map( ( column ) => column.id ) );
    this.apply();
  },

  // The grid template and the least width for these widths.
  track( w ) {
    const tracks = this.ids.map( ( id ) => w[ id ] + "px" );
    const template = [ "var(--board-side)" ].concat( tracks , [ this.END + "rem" , "minmax(0, 1fr)" ] ).join( " " );
    const fixed = this.ids.reduce( ( sum , id ) => sum + w[ id ] , 0 );
    const least = "calc(var(--board-side) + " + ( this.END + this.GAP * ( this.ids.length + 2 ) ) + "rem + " + fixed + "px)";
    return { template , least };
  },

  apply( widths ) {
    const { template , least } = this.track( widths || this.widths() );
    if ( this.rule ) {
      this.rule.style.setProperty( "grid-template-columns" , template );
      this.rule.style.setProperty( "min-width" , least );
    } else {
      const body = Dom.get( "list-body" );
      body.style.setProperty( "--board-grid" , template );
      body.style.setProperty( "--board-min" , least );
    }
  },

  // The header: a label per column, each with an edge to drag.
  head( element , columns ) {
    const cells = [ Dom.el( "div" , { class: "board-head-cell board-cell-side" , text: "#" } ) ];
    const label = ( text , id , extra ) => {
      const cell = Dom.el( "div" , {
        class: "board-head-cell" + ( extra ? " " + extra : "" ),
        attrs: { "data-col": id },
        children: [ Dom.el( "span" , { class: "board-head-label" , text: text } ) ],
      } );
      cell.appendChild( this.handle( id ) );
      return cell;
    };
    cells.push( label( I18n.get( "lists.paper_column" ) , "paper" , "board-cell-paper" ) );
    columns.forEach( ( column ) => cells.push( label( column.label , column.id ) ) );
    cells.push( Dom.el( "div" , { class: "board-head-cell" } ) );
    element.replaceChildren( ...cells );
  },

  handle( id ) {
    const handle = Dom.el( "span" , { class: "board-resize" , attrs: { title: I18n.get( "lists.resize_help" ) } } );
    handle.addEventListener( "pointerdown" , ( event ) => this.drag( event , id , handle ) );
    handle.addEventListener( "dblclick" , ( event ) => {
      event.preventDefault();
      const kept = this.stored();
      delete kept[ id ];
      this.store( kept );
      this.apply();
    } );
    return handle;
  },

  drag( event , id , handle ) {
    if ( event.button !== 0 ) return;
    event.preventDefault();
    event.stopPropagation();
    // Every column is fixed at the width it is drawn at now, so the edge
    // held is the only thing that moves.
    const widths = this.widths();
    const startX = event.clientX;
    const start = widths[ id ];
    let width = start;
    let frame = 0;
    handle.setPointerCapture( event.pointerId );
    handle.classList.add( "is-dragging" );
    document.body.classList.add( "board-resizing" );
    // While dragging, only the header and the rows on screen are resized (a
    // style on each): a long list is hundreds of rows, and resizing them all
    // every frame is what made dragging lag. The shared rule catches the
    // rest up on release.
    const board = Dom.get( "list-scroll" );
    const touched = new Set();
    const onScreen = () => {
      const view = board.getBoundingClientRect();
      const out = [ Dom.get( "list-head" ) ];
      Dom.all( "#list-rows > .board-row, #list-shelf-rows > .board-row" ).forEach( ( row ) => {
        const box = row.getBoundingClientRect();
        if ( box.bottom >= view.top && box.top <= view.bottom ) out.push( row );
      } );
      return out;
    };
    const paint = () => {
      frame = 0;
      widths[ id ] = width;
      const { template , least } = this.track( widths );
      onScreen().forEach( ( element ) => {
        touched.add( element );
        element.style.gridTemplateColumns = template;
        element.style.minWidth = least;
      } );
    };
    const move = ( moved ) => {
      width = Math.max( id === "paper" ? this.PAPER_MIN : this.MIN , Math.round( start + moved.clientX - startX ) );
      if ( !frame ) frame = window.requestAnimationFrame( paint );
    };
    const scrolled = () => {
      if ( !frame ) frame = window.requestAnimationFrame( paint );
    };
    board.addEventListener( "scroll" , scrolled , { passive: true } );
    const done = () => {
      handle.removeEventListener( "pointermove" , move );
      handle.removeEventListener( "pointerup" , done );
      handle.removeEventListener( "pointercancel" , done );
      board.removeEventListener( "scroll" , scrolled );
      if ( frame ) window.cancelAnimationFrame( frame );
      handle.classList.remove( "is-dragging" );
      document.body.classList.remove( "board-resizing" );
      widths[ id ] = width;
      this.apply( widths );
      touched.forEach( ( element ) => {
        element.style.gridTemplateColumns = "";
        element.style.minWidth = "";
      } );
      if ( width === start ) return;
      // Kept: the dragged column, and the Paper column as it is drawn.
      const kept = this.stored();
      kept[ id ] = width;
      kept.paper = widths.paper;
      this.store( kept );
    };
    handle.addEventListener( "pointermove" , move );
    handle.addEventListener( "pointerup" , done );
    handle.addEventListener( "pointercancel" , done );
  },
};
