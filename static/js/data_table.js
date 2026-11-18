// DataTable: the spreadsheet-style table every list screen shares (Library,
// Missing, Status). A Bootstrap .table inside its own scroll area, with:
//
//   - a header that stays put while the rows scroll under it;
//   - sorting by clicking a header (again flips it); a screen that sorts on
//     several tiers (Missing) shows the tie-breakers' rank;
//   - a Columns menu: show or hide each column, move it left or right, and
//     put everything back; widths are dragged on the header's right edge;
//   - all of that remembered per screen in this browser (localStorage), so a
//     reload looks the same.
//
// The screen owns the data and the fetching. It says what the columns are and
// how to draw a cell; DataTable draws the table and tells it when the order
// changed (onSort), or sorts the rows itself when there is no onSort.
//
//   const table = new DataTable( {
//     name: "missing",                      // remembered under this name
//     holder: Dom.get( "missing-table" ),   // an empty element to draw into
//     menu: Dom.get( "missing-columns" ),   // the Columns dropdown's <ul>
//     columns: [ { id , label , sort , align , width , flex , hide , lock , when , cell , value } ],
//     sort: [ { col: "conn" , desc: true } ],
//     tiers: 3,                             // how many sort tiers to keep
//     onSort: ( sort ) => reload(),
//     onEnd: () => loadMore(),              // scrolled near the bottom
//   } );
//   table.rows( list );   table.rows( more , true );   // replace, append
//
// A column: id; label (an i18n key); sort (true, or the server's sort name)
// to make the header clickable; align "end" for numbers; width in rem (the
// starting width; flex marks the one column that takes what is left, its
// width then its least); hide to start hidden; lock to keep it from being
// hidden (the title); when() to show it only sometimes (a match score while
// searching); cell( row ) answers a Node, a string or null; value( row ) is
// what a local sort compares. text, instead of label, is a header that is
// not in language.yaml (the rollup's columns come from the summaries).
class DataTable {
  static labelOf( column ) {
    return column.text != null ? String( column.text ) : I18n.get( column.label );
  }

  constructor( options ) {
    this.options = options;
    this.name = options.name;
    this.columns = options.columns;
    this.sort = ( options.sort || [] ).slice();
    this.tiers = options.tiers || 1;
    this.data = [];
    this.order = [];
    this.drawn = 0;
    this.prefs = this.load();
    this.build();
    this.drawMenu();
  }

  // -- what is remembered ----------------------------------------------------

  storageKey() {
    return "table." + this.name;
  }

  load() {
    let prefs = {};
    try {
      prefs = JSON.parse( window.localStorage.getItem( this.storageKey() ) || "{}" ) || {};
    } catch ( error ) {
      prefs = {};
    }
    return { order: Array.isArray( prefs.order ) ? prefs.order : [] , shown: prefs.shown || {} , widths: prefs.widths || {} };
  }

  save() {
    try {
      window.localStorage.setItem( this.storageKey() , JSON.stringify( this.prefs ) );
    } catch ( error ) { /* only a convenience */ }
  }

  reset() {
    this.prefs = { order: [] , shown: {} , widths: {} };
    try {
      window.localStorage.removeItem( this.storageKey() );
    } catch ( error ) { /* only a convenience */ }
    this.redraw();
  }

  // Every column in the reader's order: the remembered order first, then any
  // column added since, where the code puts it.
  ordered() {
    const byId = new Map( this.columns.map( ( column ) => [ column.id , column ] ) );
    const out = [];
    this.prefs.order.forEach( ( id ) => {
      if ( byId.has( id ) ) {
        out.push( byId.get( id ) );
        byId.delete( id );
      }
    } );
    this.columns.forEach( ( column ) => {
      if ( !byId.has( column.id ) ) return;
      const at = this.columns.indexOf( column );
      const before = out.findIndex( ( placed ) => this.columns.indexOf( placed ) > at );
      if ( before < 0 ) out.push( column );
      else out.splice( before , 0 , column );
      byId.delete( column.id );
    } );
    return out;
  }

  chosen( column ) {
    if ( column.lock ) return true;
    const shown = this.prefs.shown[ column.id ];
    return shown === undefined ? !column.hide : Boolean( shown );
  }

  // What is drawn: chosen, and wanted right now.
  visible() {
    return this.ordered().filter( ( column ) => this.chosen( column ) && ( !column.when || column.when() ) );
  }

  // The width a column is drawn at: the one dragged, else its default. The
  // flex column, until it is dragged (or another edge is), fills what the
  // others leave of the area, so a fresh table is as wide as its screen.
  widthOf( column , room ) {
    const px = this.prefs.widths[ column.id ];
    if ( px ) return px;
    const rem = parseFloat( getComputedStyle( document.documentElement ).fontSize ) || 16;
    const own = Math.round( ( column.width || 8 ) * rem );
    if ( !column.flex || room === undefined ) return own;
    return Math.max( own , room );
  }

  // Every shown column's width now, by id.
  widths() {
    const columns = this.visible();
    const out = {};
    let others = 0;
    columns.forEach( ( column ) => {
      if ( column.flex ) return;
      out[ column.id ] = this.widthOf( column );
      others += out[ column.id ];
    } );
    const area = this.scroll ? this.scroll.clientWidth : 0;
    columns.forEach( ( column ) => {
      if ( column.flex ) out[ column.id ] = this.widthOf( column , area - others - 2 );
    } );
    return out;
  }

  // -- the table ---------------------------------------------------------------

  build() {
    const holder = this.options.holder;
    Dom.clear( holder );
    this.colgroup = Dom.el( "colgroup" );
    this.headRow = Dom.el( "tr" );
    this.body = Dom.el( "tbody" );
    this.table = Dom.el( "table" , {
      class: "table table-sm table-hover table-striped align-middle mb-0 data-table",
      children: [ this.colgroup , Dom.el( "thead" , { class: "table-light" , children: [ this.headRow ] } ) , this.body ],
    } );
    this.scroll = Dom.el( "div" , { class: "table-responsive" , attrs: { tabindex: "0" } , children: [ this.table ] } );
    this.scroll.classList.add( "data-table-scroll" );
    holder.appendChild( this.scroll );
    // A wider or narrower area changes what the flex column fills.
    new ResizeObserver( () => this.size() ).observe( this.scroll );
    // Near the end of what is drawn: draw the next rows already here, or ask
    // the screen for more (onEnd). From md the rows scroll inside the area;
    // on a phone the page scrolls, so both are watched.
    const near = () => {
      if ( this.nearing ) return;
      this.nearing = window.requestAnimationFrame( () => {
        this.nearing = 0;
        this.whenNearEnd( true );
      } );
    };
    this.scroll.addEventListener( "scroll" , near , { passive: true } );
    window.addEventListener( "scroll" , near , { passive: true } );
    this.drawHead();
  }

  drawHead() {
    const columns = this.visible();
    Dom.clear( this.colgroup );
    Dom.clear( this.headRow );
    columns.forEach( ( column ) => {
      this.colgroup.appendChild( Dom.el( "col" , { attrs: { "data-col": column.id } } ) );
      this.headRow.appendChild( this.headCell( column ) );
    } );
    // After the last column, a blank one takes any room to spare, so the
    // header and the rows' stripes run to the right edge without any real
    // column stretching. When the columns add up to more, it is 0 wide and
    // the area scrolls sideways.
    this.colgroup.appendChild( Dom.el( "col" , { class: "data-table-filler" } ) );
    this.headRow.appendChild( Dom.el( "th" , { class: "data-table-filler" , attrs: { "aria-hidden": "true" } } ) );
    this.size();
    this.paintSort();
  }

  // Puts every <col> at its width, and the table at least as wide as all of
  // them. widths: what to draw (a drag in progress), else the kept ones.
  size( widths ) {
    if ( !this.colgroup ) return;
    const w = widths || this.widths();
    let least = 0;
    Array.from( this.colgroup.children ).forEach( ( col ) => {
      const id = col.getAttribute( "data-col" );
      if ( !id ) return;
      col.style.width = w[ id ] + "px";
      least += w[ id ];
    } );
    this.table.style.minWidth = least + "px";
  }

  headCell( column ) {
    const th = Dom.el( "th" , { class: "data-table-th" + ( column.align === "end" ? " text-end" : "" ) , attrs: { scope: "col" , "data-col": column.id } } );
    const label = Dom.el( "span" , { text: DataTable.labelOf( column ) } );
    if ( column.title ) th.setAttribute( "title" , I18n.get( column.title ) );
    if ( column.sort ) {
      th.appendChild( Dom.el( "button" , {
        class: "data-table-sort",
        attrs: { type: "button" },
        children: [ label , Dom.el( "span" , { class: "data-table-mark" , attrs: { "aria-hidden": "true" } } ) ],
        on: { click: () => this.sortBy( column ) },
      } ) );
    } else {
      th.appendChild( label );
    }
    const grip = Dom.el( "span" , { class: "data-table-grip" , attrs: { "aria-hidden": "true" } } );
    grip.addEventListener( "pointerdown" , ( event ) => this.drag( event , column , grip ) );
    grip.addEventListener( "click" , ( event ) => event.stopPropagation() );
    grip.addEventListener( "dblclick" , ( event ) => {
      event.stopPropagation();
      delete this.prefs.widths[ column.id ];
      this.save();
      this.size();
    } );
    th.appendChild( grip );
    return th;
  }

  // Dragging a header's right edge: that edge follows the pointer and
  // nothing else moves, like a spreadsheet. Every column is held at the width
  // it is drawn at when the drag starts (the flex column too, from then on).
  drag( event , column , grip ) {
    if ( event.button !== 0 ) return;
    event.preventDefault();
    event.stopPropagation();
    const widths = this.widths();
    const start = widths[ column.id ];
    const startX = event.clientX;
    let width = start;
    let frame = 0;
    grip.setPointerCapture( event.pointerId );
    grip.classList.add( "is-dragging" );
    document.body.classList.add( "data-table-dragging" );
    const move = ( moved ) => {
      width = Math.max( 48 , Math.round( start + moved.clientX - startX ) );
      if ( frame ) return;
      frame = window.requestAnimationFrame( () => {
        frame = 0;
        widths[ column.id ] = width;
        this.size( widths );
      } );
    };
    const done = () => {
      grip.removeEventListener( "pointermove" , move );
      grip.removeEventListener( "pointerup" , done );
      grip.removeEventListener( "pointercancel" , done );
      if ( frame ) window.cancelAnimationFrame( frame );
      grip.classList.remove( "is-dragging" );
      document.body.classList.remove( "data-table-dragging" );
      if ( width === start ) return;
      widths[ column.id ] = width;
      const flex = this.visible().find( ( each ) => each.flex );
      this.prefs.widths[ column.id ] = width;
      if ( flex ) this.prefs.widths[ flex.id ] = widths[ flex.id ];
      this.size();
      this.save();
    };
    grip.addEventListener( "pointermove" , move );
    grip.addEventListener( "pointerup" , done );
    grip.addEventListener( "pointercancel" , done );
  }

  // -- sorting -----------------------------------------------------------------

  sortName( column ) {
    return column.sort === true ? column.id : column.sort;
  }

  // Clicking the first sort column flips it; any other becomes the first, the
  // earlier ones kept behind it as tie-breakers (up to tiers).
  sortBy( column ) {
    const name = this.sortName( column );
    const first = this.sort[ 0 ];
    if ( first && first.col === name ) {
      first.desc = !first.desc;
    } else {
      const rest = this.sort.filter( ( entry ) => entry.col !== name );
      const desc = column.firstDesc === undefined ? column.align === "end" : column.firstDesc;
      this.sort = [ { col: name , desc: desc } , ...rest ].slice( 0 , this.tiers );
    }
    this.paintSort();
    if ( this.options.onSort ) this.options.onSort( this.sort );
    else this.draw();
  }

  setSort( sort ) {
    this.sort = sort.slice();
    this.paintSort();
  }

  // The sort tiers that count right now: one on a column that is not shown
  // (a match score while not searching) is skipped.
  activeSort() {
    const names = new Set( this.columns.filter( ( column ) => column.sort && ( !column.when || column.when() ) ).map( ( column ) => this.sortName( column ) ) );
    return this.sort.filter( ( entry ) => names.has( entry.col ) );
  }

  paintSort() {
    const active = this.activeSort();
    Array.from( this.headRow.children ).forEach( ( th ) => {
      const column = this.columns.find( ( each ) => each.id === th.getAttribute( "data-col" ) );
      const mark = th.querySelector( ".data-table-mark" );
      if ( !mark ) return;
      const rank = active.findIndex( ( entry ) => entry.col === this.sortName( column ) );
      const entry = active[ rank ];
      th.setAttribute( "aria-sort" , rank === 0 ? ( entry.desc ? "descending" : "ascending" ) : "none" );
      th.classList.toggle( "is-sorted" , rank >= 0 );
      Dom.clear( mark );
      if ( rank < 0 ) {
        mark.appendChild( Dom.el( "i" , { class: "bi bi-chevron-expand" } ) );
        return;
      }
      mark.appendChild( Dom.el( "i" , { class: "bi bi-caret-" + ( entry.desc ? "down" : "up" ) + "-fill" } ) );
      if ( active.length > 1 ) mark.appendChild( Dom.el( "sup" , { text: String( rank + 1 ) } ) );
    } );
  }

  // A table with no onSort sorts its own rows (every row is on the page).
  sorted( rows ) {
    if ( this.options.onSort ) return rows;
    const active = this.activeSort();
    if ( !active.length ) return rows;
    const byName = new Map( this.columns.map( ( column ) => [ this.sortName( column ) , column ] ) );
    const compare = ( a , b ) => {
      if ( a === b ) return 0;
      if ( a == null || a === "" ) return 1;
      if ( b == null || b === "" ) return -1;
      if ( typeof a === "number" && typeof b === "number" ) return a - b;
      return String( a ).localeCompare( String( b ) , undefined , { numeric: true , sensitivity: "base" } );
    };
    return rows.slice().sort( ( x , y ) => {
      for ( const entry of active ) {
        const column = byName.get( entry.col );
        const value = column.value || ( ( row ) => row[ column.id ] );
        const a = value( x );
        const b = value( y );
        // Blanks stay last either way.
        const blank = ( a == null || a === "" ) - ( b == null || b === "" );
        if ( blank ) return blank;
        const order = compare( a , b );
        if ( order ) return entry.desc ? -order : order;
      }
      return 0;
    } );
  }

  // -- rows --------------------------------------------------------------------

  // Rows are drawn CHUNK at a time: the first ones at once, the next as the
  // reader scrolls near the end of them (whenNearEnd). A screen of a couple
  // of thousand rows (Code, Datasets) used to build every one on each search
  // keystroke and each sort, tens of thousands of elements, and lay them all
  // out; now it builds what can be seen and a little more. this.order is
  // every row in the order shown; this.drawn how many of them are on the page.
  rows( list , append ) {
    this.data = append ? this.data.concat( list ) : list.slice();
    if ( append && this.options.onSort ) {
      // A page the server sent because the reader scrolled to the end: shown.
      this.order = this.order.concat( list );
      this.fill( this.order.length );
      return;
    }
    if ( !append ) this.scroll.scrollTop = 0;
    this.draw();
  }

  // keep: draw as many rows as are drawn now (columns changed, not the rows).
  draw( keep ) {
    const had = this.drawn || 0;
    this.order = this.sorted( this.data );
    this.drawn = 0;
    Dom.clear( this.body );
    this.fill( keep ? Math.max( had , DataTable.CHUNK ) : DataTable.CHUNK );
    this.whenNearEnd();
  }

  // Draws rows until upto are on the page (or every row is).
  fill( upto ) {
    const end = Math.min( upto , this.order.length );
    if ( end <= this.drawn ) return;
    const columns = this.visible();
    const rows = document.createDocumentFragment();
    for ( let at = this.drawn ; at < end ; at++ ) rows.appendChild( this.row( this.order[ at ] , columns ) );
    this.body.appendChild( rows );
    this.drawn = end;
  }

  // Within a screen or two of the last drawn row: draw the next chunk, or,
  // with all of them drawn and the reader scrolling, ask for the next page.
  // Also run after a draw, so a short first chunk on a tall screen is
  // followed at once.
  whenNearEnd( scrolled ) {
    if ( !this.table.isConnected || !this.scroll.offsetParent ) return;
    const box = this.scroll.getBoundingClientRect();
    const seen = Math.min( box.bottom , window.innerHeight );
    const left = this.table.getBoundingClientRect().bottom - seen;
    if ( left > Math.max( 600 , window.innerHeight ) ) return;
    if ( this.drawn < this.order.length ) {
      this.fill( this.drawn + DataTable.CHUNK );
      // Still short (a very tall screen): look again next frame.
      window.requestAnimationFrame( () => this.whenNearEnd() );
      return;
    }
    if ( scrolled && this.options.onEnd && !this.ending && this.data.length ) {
      this.ending = true;
      Promise.resolve( this.options.onEnd() ).finally( () => { this.ending = false; } );
    }
  }

  row( row , columns ) {
    const tr = Dom.el( "tr" );
    columns.forEach( ( column ) => {
      const td = Dom.el( "td" , { class: [ column.align === "end" ? "text-end" : "" , column.cellClass || "" ].join( " " ).trim() } );
      td.setAttribute( "data-label" , DataTable.labelOf( column ) );
      const value = column.cell ? column.cell( row ) : row[ column.id ];
      if ( value instanceof Node ) td.appendChild( value );
      else if ( value != null ) td.textContent = String( value );
      tr.appendChild( td );
    } );
    tr.appendChild( Dom.el( "td" , { class: "data-table-filler" , attrs: { "aria-hidden": "true" } } ) );
    if ( this.options.rowClass ) {
      const extra = this.options.rowClass( row );
      if ( extra ) tr.className = extra;
    }
    return tr;
  }

  // Columns changed (shown, hidden, moved, a when() flipped): head and rows again.
  redraw() {
    this.drawHead();
    this.draw( true );
    this.drawMenu();
  }

  // -- the Columns menu --------------------------------------------------------

  drawMenu() {
    const menu = this.options.menu;
    if ( !menu ) return;
    Dom.clear( menu );
    menu.appendChild( Dom.el( "li" , { children: [ Dom.el( "h6" , { class: "dropdown-header" , text: I18n.get( "table.columns_heading" ) } ) ] } ) );
    const ordered = this.ordered();
    ordered.forEach( ( column , index ) => {
      const id = "table-" + this.name + "-col-" + column.id;
      const box = Dom.el( "input" , { class: "form-check-input mt-0" , attrs: { type: "checkbox" , id: id } } );
      box.checked = this.chosen( column );
      box.disabled = Boolean( column.lock );
      box.addEventListener( "change" , () => {
        this.prefs.shown[ column.id ] = box.checked;
        this.save();
        this.redraw();
      } );
      const move = ( step , icon , key ) => Dom.el( "button" , {
        class: "btn btn-sm btn-link data-table-move",
        attrs: { type: "button" , title: I18n.get( key ) , "aria-label": I18n.get( key ) + ": " + DataTable.labelOf( column ) },
        children: [ Dom.el( "i" , { class: "bi bi-" + icon , attrs: { "aria-hidden": "true" } } ) ],
        on: { click: () => this.move( column , step ) },
      } );
      const up = move( -1 , "arrow-up" , "table.move_left" );
      const down = move( 1 , "arrow-down" , "table.move_right" );
      up.disabled = index === 0;
      down.disabled = index === ordered.length - 1;
      menu.appendChild( Dom.el( "li" , { children: [ Dom.el( "div" , {
        class: "dropdown-item-text d-flex align-items-center gap-2 data-table-menu-item",
        children: [
          box,
          Dom.el( "label" , { class: "form-check-label flex-grow-1 text-nowrap" , text: DataTable.labelOf( column ) , attrs: { for: id } } ),
          up, down,
        ],
      } ) ] } ) );
    } );
    menu.appendChild( Dom.el( "li" , { children: [ Dom.el( "hr" , { class: "dropdown-divider" } ) ] } ) );
    menu.appendChild( Dom.el( "li" , { children: [ Dom.el( "button" , {
      class: "dropdown-item",
      attrs: { type: "button" },
      children: [ Dom.el( "i" , { class: "bi bi-arrow-counterclockwise me-2" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: I18n.get( "table.reset_columns" ) } ) ],
      on: { click: () => this.reset() },
    } ) ] } ) );
  }

  move( column , step ) {
    const order = this.ordered().map( ( each ) => each.id );
    const at = order.indexOf( column.id );
    const to = at + step;
    if ( to < 0 || to >= order.length ) return;
    order.splice( at , 1 );
    order.splice( to , 0 , column.id );
    this.prefs.order = order;
    this.save();
    this.redraw();
    // Keep the moved column's arrow under the pointer's focus.
    const box = document.getElementById( "table-" + this.name + "-col-" + column.id );
    if ( box ) box.closest( "li" ).querySelector( step < 0 ? ".data-table-move" : ".data-table-move:last-child" ).focus();
  }
}

// A Filter button: its dropdown holds every filter the screen has, and the
// button shows how many are on. count() answers that number; clear() puts
// them all back. The menu's own "Clear" button is [data-filter-clear].
DataTable.filters = function ( button , count , clear ) {
  const badge = button.querySelector( ".badge" );
  const paint = () => {
    const n = count();
    if ( badge ) {
      Dom.text( badge , n ? String( n ) : "" );
      Dom.show( badge , n > 0 );
    }
    button.classList.toggle( "btn-primary" , n > 0 );
    button.classList.toggle( "btn-outline-secondary" , n === 0 );
  };
  const menu = button.parentElement.querySelector( ".dropdown-menu" );
  const reset = menu && menu.querySelector( "[data-filter-clear]" );
  if ( reset ) Dom.onPress( reset , () => { clear(); paint(); } );
  if ( menu ) {
    menu.addEventListener( "change" , paint );
    menu.addEventListener( "input" , paint );
  }
  paint();
  return paint;
};

// How many rows a table draws at a time (see DataTable.rows).
DataTable.CHUNK = 100;
