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
// what a local sort compares.
class DataTable {
  constructor( options ) {
    this.options = options;
    this.name = options.name;
    this.columns = options.columns;
    this.sort = ( options.sort || [] ).slice();
    this.tiers = options.tiers || 1;
    this.data = [];
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

  widthOf( column ) {
    const px = this.prefs.widths[ column.id ];
    return px || Math.round( ( column.width || 8 ) * 16 );
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
    if ( this.options.onEnd ) {
      this.scroll.addEventListener( "scroll" , () => {
        const left = this.scroll.scrollHeight - this.scroll.scrollTop - this.scroll.clientHeight;
        if ( left < 240 && !this.ending ) {
          this.ending = true;
          Promise.resolve( this.options.onEnd() ).finally( () => { this.ending = false; } );
        }
      } , { passive: true } );
    }
    this.drawHead();
  }

  drawHead() {
    const columns = this.visible();
    Dom.clear( this.colgroup );
    Dom.clear( this.headRow );
    let least = 0;
    columns.forEach( ( column ) => {
      const width = this.widthOf( column );
      least += width;
      const col = Dom.el( "col" );
      if ( !column.flex ) col.style.width = width + "px";
      this.colgroup.appendChild( col );
      this.headRow.appendChild( this.headCell( column ) );
    } );
    // Never narrower than its columns: past that the area scrolls sideways.
    this.table.style.minWidth = least + "px";
    this.paintSort();
  }

  headCell( column ) {
    const th = Dom.el( "th" , { class: "data-table-th" + ( column.align === "end" ? " text-end" : "" ) , attrs: { scope: "col" , "data-col": column.id } } );
    const label = Dom.el( "span" , { text: I18n.get( column.label ) } );
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
    grip.addEventListener( "pointerdown" , ( event ) => this.drag( event , column , th ) );
    grip.addEventListener( "dblclick" , () => {
      delete this.prefs.widths[ column.id ];
      this.save();
      this.redraw();
    } );
    th.appendChild( grip );
    return th;
  }

  // Dragging a header's right edge sets that column's width.
  drag( event , column , th ) {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const start = th.getBoundingClientRect().width;
    const index = Array.from( this.headRow.children ).indexOf( th );
    const col = this.colgroup.children[ index ];
    document.body.classList.add( "data-table-dragging" );
    const move = ( moved ) => {
      const width = Math.max( 48 , Math.round( start + moved.clientX - startX ) );
      this.prefs.widths[ column.id ] = width;
      if ( !column.flex ) col.style.width = width + "px";
      this.table.style.minWidth = this.visible().reduce( ( sum , each ) => sum + this.widthOf( each ) , 0 ) + "px";
    };
    const up = () => {
      document.removeEventListener( "pointermove" , move );
      document.removeEventListener( "pointerup" , up );
      document.body.classList.remove( "data-table-dragging" );
      this.save();
    };
    document.addEventListener( "pointermove" , move );
    document.addEventListener( "pointerup" , up );
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

  rows( list , append ) {
    this.data = append ? this.data.concat( list ) : list.slice();
    if ( append && this.options.onSort ) {
      const columns = this.visible();
      list.forEach( ( row ) => this.body.appendChild( this.row( row , columns ) ) );
      return;
    }
    if ( !append ) this.scroll.scrollTop = 0;
    this.draw();
  }

  draw() {
    const columns = this.visible();
    Dom.clear( this.body );
    this.sorted( this.data ).forEach( ( row ) => this.body.appendChild( this.row( row , columns ) ) );
  }

  row( row , columns ) {
    const tr = Dom.el( "tr" );
    columns.forEach( ( column ) => {
      const td = Dom.el( "td" , { class: [ column.align === "end" ? "text-end" : "" , column.cellClass || "" ].join( " " ).trim() } );
      td.setAttribute( "data-label" , I18n.get( column.label ) );
      const value = column.cell ? column.cell( row ) : row[ column.id ];
      if ( value instanceof Node ) td.appendChild( value );
      else if ( value != null ) td.textContent = String( value );
      tr.appendChild( td );
    } );
    if ( this.options.rowClass ) {
      const extra = this.options.rowClass( row );
      if ( extra ) tr.className = extra;
    }
    return tr;
  }

  // Columns changed (shown, hidden, moved, a when() flipped): head and rows again.
  redraw() {
    this.drawHead();
    this.draw();
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
        attrs: { type: "button" , title: I18n.get( key ) , "aria-label": I18n.get( key ) + ": " + I18n.get( column.label ) },
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
          Dom.el( "label" , { class: "form-check-label flex-grow-1 text-nowrap" , text: I18n.get( column.label ) , attrs: { for: id } } ),
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
