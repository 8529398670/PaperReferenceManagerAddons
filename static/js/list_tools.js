// The Lists screen's tools: the tag chip bar, row selection, the tag and text
// filter, painting a tag onto rows, ordering the list, and getting around a
// long one (jump to #, an anchor, top and bottom). Everything here is a
// visible button or box: no held keys, no hidden gestures.
//
// Chip bar: every tag in the list's vocabulary, in its order (drag a chip to
// move it; the order is part of the list, so every browser sees it).
//   - with rows selected, a chip puts that tag on all of them, or takes it off
//     when they all have it (one change, one undo step);
//   - with none selected, a chip is "armed": each row clicked next gets it,
//     until Esc or the chip again (painting);
//   - with Filter on, a chip adds the tag to the filter instead: any (one is
//     enough), all (every one), none (rows carrying none of them).
//
// Selection: click a row, Cmd/Ctrl-click to add one, Shift-click for a range;
// Esc clears it. Dragging a selected row moves the whole selection.
const ListTools = {
  lists: null,
  selected: new Set(),
  selAnchor: null,
  armed: null,
  filterOn: false,
  filterTags: [],
  match: "any",
  text: "",
  showExtra: false,
  draggingChip: null,
  INTERACTIVE: "input, textarea, select, button, a, .board-cell, .board-row-grip, label",

  init( lists ) {
    this.lists = lists;
    this.showExtra = lists.local( "list-extra" ) === "1";
    Dom.get( "list-extra" ).checked = this.showExtra;
    // A long vocabulary folds to a few lines until asked for.
    this.allTags = lists.local( "list-all-tags" ) === "1";
    Dom.get( "list-chips-more" ).addEventListener( "click" , () => {
      this.allTags = !this.allTags;
      lists.local( "list-all-tags" , this.allTags ? "1" : "0" );
      this.drawBar();
    } );
    Dom.get( "list-extra" ).addEventListener( "change" , ( event ) => {
      this.showExtra = event.target.checked;
      lists.local( "list-extra" , this.showExtra ? "1" : "0" );
      lists.draw();
    } );
    Dom.get( "list-filter" ).addEventListener( "input" , ( event ) => {
      this.text = event.target.value;
      lists.draw();
    } );
    Dom.get( "list-filter-on" ).addEventListener( "change" , ( event ) => {
      this.filterOn = event.target.checked;
      if ( this.filterOn ) this.disarm();
      lists.draw();
    } );
    // The Filter button counts the tags filtering; its Clear turns it all off.
    this.paintFilter = DataTable.filters( Dom.get( "list-filter-button" ) ,
      () => ( this.filterOn ? Math.max( 1 , this.filterTags.length ) : 0 ),
      () => {
        this.filterOn = false;
        this.filterTags = [];
        lists.draw();
      } );
    Dom.onPress( Dom.get( "list-columns-edit" ) , () => ListPanels.columns() );
    Dom.get( "list-filter-match" ).addEventListener( "change" , ( event ) => {
      this.match = event.target.value;
      lists.draw();
    } );
    const find = Dom.get( "list-tag-find" );
    find.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      const wanted = find.value.trim().toLowerCase();
      const name = this.tagNames().find( ( tag ) => tag.toLowerCase() === wanted )
        || this.tagNames().find( ( tag ) => tag.toLowerCase().includes( wanted ) );
      if ( !wanted || !name ) return;
      find.value = "";
      this.filterOn = true;
      Dom.get( "list-filter-on" ).checked = true;
      if ( !this.filterTags.includes( name ) ) this.filterTags.push( name );
      lists.draw();
    } );

    const rows = Dom.get( "list-rows" );
    rows.addEventListener( "click" , ( event ) => this.onRowClick( event ) );
    // Shift-click picks a range of rows, not a range of text.
    rows.addEventListener( "mousedown" , ( event ) => {
      if ( event.shiftKey && !event.target.closest( this.INTERACTIVE ) ) event.preventDefault();
    } );
    document.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Escape" || Nav.current() !== "lists" || document.querySelector( ".modal.show" ) ) return;
      if ( event.target.closest && event.target.closest( "input, textarea, select" ) ) return;
      if ( this.armed || this.selected.size ) {
        this.disarm();
        this.clearSelection();
      }
    } );

    // Order by, once.
    const order = Dom.get( "list-order-items" );
    [ [ "tags" , "lists.order_tags" ] , [ "year" , "lists.order_year_desc" ] , [ "year_asc" , "lists.order_year_asc" ] ,
      [ "cites" , "lists.order_cites" ] , [ "title" , "lists.order_title" ] , [ "added" , "lists.order_added" ] ].forEach( ( [ by , key ] ) => {
      const button = Dom.el( "button" , { class: "dropdown-item" , attrs: { type: "button" } , text: I18n.get( key ) , on: { click: () => this.orderBy( by ) } } );
      if ( by === "cites" ) {
        // OpenAlex counts arrive with the per-paper content (phase 4).
        button.disabled = true;
        button.title = I18n.get( "lists.order_cites_later" );
        button.appendChild( Dom.el( "div" , { class: "small text-body-secondary" , text: I18n.get( "lists.order_cites_later" ) } ) );
      }
      order.appendChild( Dom.el( "li" , { children: [ button ] } ) );
    } );
    Dom.get( "list-auto-move" ).addEventListener( "change" , ( event ) => this.option( "auto_move" , event.target.checked ) );
    Dom.get( "list-add-where" ).addEventListener( "change" , ( event ) => this.option( "add_where" , event.target.value ) );

    // Getting around.
    const jump = Dom.get( "list-jump" );
    jump.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      this.jump( parseInt( jump.value , 10 ) );
    } );
    Dom.get( "list-to-anchor" ).addEventListener( "click" , () => {
      const key = this.anchor();
      if ( key && !BoardView.flash( rows , key ) ) Dom.toast( I18n.get( "lists.hidden_by_filter" ) , "error" );
    } );
    Dom.get( "list-to-top" ).addEventListener( "click" , () => {
      Dom.movedOnPurpose();
      Dom.get( "lists-panel" ).scrollIntoView( { behavior: "smooth" } );
    } );
    Dom.get( "list-to-bottom" ).addEventListener( "click" , () => {
      const last = rows.lastElementChild;
      if ( !last ) return;
      Dom.movedOnPurpose();
      last.scrollIntoView( { block: "end" , behavior: "smooth" } );
    } );
  },

  // A new list: nothing picked, painted or filtered by tag carries over.
  forget() {
    this.selected.clear();
    this.selAnchor = null;
    this.armed = null;
    this.filterTags = [];
  },

  // ---- the tag names, and the bar ------------------------------------------------

  // The vocabulary in its order, then any tag rows carry that it lacks.
  tagNames() {
    const view = this.lists.view;
    if ( !view ) return [];
    const seen = new Set();
    const out = [];
    const push = ( name ) => {
      if ( name && !seen.has( name.toLowerCase() ) ) {
        seen.add( name.toLowerCase() );
        out.push( name );
      }
    };
    ( ( view.doc.vocab && view.doc.vocab.tags ) || [] ).forEach( ( tag ) => push( tag.name ) );
    ( view.doc.items || [] ).concat( view.doc.staging || [] ).forEach( ( item ) => ( item.tags || [] ).forEach( push ) );
    return out;
  },

  counts() {
    const counts = new Map();
    ( this.lists.view.doc.items || [] ).forEach( ( item ) => ( item.tags || [] ).forEach( ( tag ) => {
      counts.set( tag.toLowerCase() , ( counts.get( tag.toLowerCase() ) || 0 ) + 1 );
    } ) );
    return counts;
  },

  drawBar() {
    const view = this.lists.view;
    const locked = view.locked;
    const options = view.doc.options || {};
    Dom.get( "list-auto-move" ).checked = Boolean( options.auto_move );
    Dom.get( "list-add-where" ).value = options.add_where || "bottom";
    Dom.get( "list-filter-on" ).checked = this.filterOn;
    Dom.show( Dom.get( "list-filter-match" ) , this.filterOn );
    Dom.get( "list-filter-match" ).value = this.match;
    Dom.get( "list-to-anchor" ).disabled = !this.anchor();
    const folded = ( options.fold_cols || [] ).filter( ( id ) => ( view.doc.columns || [] ).some( ( column ) => column.id === id ) ).length;
    Dom.text( Dom.get( "list-extra-label" ) , I18n.get( "lists.extra_columns" ).replace( "{count}" , folded ) );
    Dom.show( Dom.get( "list-extra-holder" ) , folded > 0 );
    Dom.text( Dom.get( "list-filter-tags" ) , this.filterOn ? this.filterTags.join( ", " ) : "" );
    if ( this.paintFilter ) this.paintFilter();

    const vocab = ( view.doc.vocab && view.doc.vocab.tags ) || [];
    const counts = this.counts();
    const selected = this.selectedKeys();
    const chips = this.tagNames().map( ( name ) => {
      const lower = name.toLowerCase();
      const filtering = this.filterOn && this.filterTags.some( ( tag ) => tag.toLowerCase() === lower );
      const onAll = selected.length > 0 && selected.every( ( key ) => ( ( this.lists.row( key ) || {} ).tags || [] ).some( ( tag ) => tag.toLowerCase() === lower ) );
      const chip = Dom.el( "button" , {
        class: "tag-chip tag-chip-bar" + ( filtering ? " is-filter" : "" ) + ( this.armed === name ? " is-armed" : "" ) + ( onAll ? " is-on" : "" ),
        attrs: { type: "button" , "aria-pressed": String( filtering || this.armed === name || onAll ) , title: this.chipHelp( selected.length ) },
        children: [
          Dom.el( "span" , { text: name } ),
          Dom.el( "span" , { class: "tag-chip-count" , text: String( counts.get( lower ) || 0 ) } ),
        ],
        on: { click: () => this.onChip( name ) },
      } );
      TagColors.paint( chip , name , vocab );
      if ( !locked ) this.chipDraggable( chip , name );
      return chip;
    } );
    if ( !locked ) {
      const fresh = Dom.el( "input" , {
        class: "form-control form-control-sm tag-input",
        attrs: { type: "text" , autocomplete: "off" , placeholder: I18n.get( "lists.new_tag" ) , "aria-label": I18n.get( "lists.new_tag" ) , "data-chip-new": "" },
      } );
      fresh.addEventListener( "keydown" , ( event ) => {
        if ( event.key !== "Enter" ) return;
        event.preventDefault();
        const name = fresh.value.trim();
        if ( !name || this.lists.vocabEntry( name ) ) return;
        const ops = [];
        const back = [];
        this.lists.createTag( name , ops , back );
        this.lists.change( "undo.list_tag_new" , ops , back ).then( () => {
          const again = Dom.get( "list-chips" ).querySelector( "[data-chip-new]" );
          if ( again ) again.focus();
        } );
      } );
      chips.push( fresh );
    }
    const bar = Dom.get( "list-chips" );
    const typing = bar.contains( document.activeElement ) && document.activeElement.matches( "input" ) ? document.activeElement.value : null;
    bar.replaceChildren( ...chips );
    if ( typing !== null ) {
      const input = bar.querySelector( "[data-chip-new]" );
      if ( input && typing ) {
        input.value = typing;
        input.focus();
      }
    }
    bar.classList.toggle( "is-folded" , !this.allTags );
    const more = Dom.get( "list-chips-more" );
    const overflowing = this.allTags || bar.scrollHeight > bar.clientHeight + 2;
    Dom.show( more , overflowing );
    more.setAttribute( "aria-expanded" , String( this.allTags ) );
    Dom.text( more , this.allTags ? I18n.get( "lists.fewer_tags" ) : I18n.get( "lists.all_tags" ).replace( "{count}" , chips.length - ( locked ? 0 : 1 ) ) );
    const paint = Dom.get( "list-paint" );
    Dom.show( paint , Boolean( this.armed ) );
    if ( this.armed ) Dom.text( paint , I18n.get( "lists.painting" ).replace( "{tag}" , () => this.armed ) );
    const selection = Dom.get( "list-selection" );
    Dom.show( selection , selected.length > 0 );
    Dom.text( selection , I18n.get( "lists.selected" ).replace( "{count}" , selected.length ) );
    Dom.show( Dom.get( "list-copy-to" ) , selected.length > 0 );
  },

  chipHelp( selected ) {
    if ( this.filterOn ) return I18n.get( "lists.chip_help_filter" );
    if ( this.lists.view.locked ) return "";
    return I18n.get( selected ? "lists.chip_help_selection" : "lists.chip_help_paint" );
  },

  onChip( name ) {
    if ( this.filterOn ) {
      const at = this.filterTags.findIndex( ( tag ) => tag.toLowerCase() === name.toLowerCase() );
      if ( at >= 0 ) this.filterTags.splice( at , 1 );
      else this.filterTags.push( name );
      this.lists.draw();
      return;
    }
    if ( this.lists.view.locked ) return;
    const selected = this.selectedKeys();
    if ( selected.length ) {
      const all = selected.every( ( key ) => ( ( this.lists.row( key ) || {} ).tags || [] ).some( ( tag ) => tag.toLowerCase() === name.toLowerCase() ) );
      return all ? this.lists.removeTag( selected , name ) : this.lists.addTag( selected , name );
    }
    this.armed = this.armed === name ? null : name;
    this.lists.draw();
  },

  disarm() {
    if ( !this.armed ) return;
    this.armed = null;
    if ( this.lists.view ) this.lists.draw();
  },

  // Drag a chip onto another to put it before (or after) that one.
  chipDraggable( chip , name ) {
    chip.draggable = true;
    chip.addEventListener( "dragstart" , ( event ) => {
      this.draggingChip = name;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData( "text/plain" , name );
    } );
    chip.addEventListener( "dragend" , () => { this.draggingChip = null; } );
    chip.addEventListener( "dragover" , ( event ) => {
      if ( this.draggingChip && this.draggingChip !== name ) event.preventDefault();
    } );
    chip.addEventListener( "drop" , ( event ) => {
      event.preventDefault();
      const moving = this.draggingChip;
      if ( !moving || moving === name ) return;
      const box = chip.getBoundingClientRect();
      const after = event.clientX > box.left + box.width / 2;
      const before = this.tagNames();
      const order = before.filter( ( tag ) => tag !== moving );
      order.splice( order.indexOf( name ) + ( after ? 1 : 0 ) , 0 , moving );
      this.lists.change( "undo.list_tag_order" , [ { op: "tag_order" , names: order } ] , [ { op: "tag_order" , names: before } ] );
    } );
  },

  // ---- filtering ------------------------------------------------------------------

  fold( text ) {
    return String( text || "" ).normalize( "NFKD" ).replace( /[̀-ͯ]/g , "" ).toLowerCase().trim();
  },

  filtering() {
    return this.fold( this.text ) !== "" || ( this.filterOn && this.filterTags.length > 0 );
  },

  matches( item , paper ) {
    if ( this.filterOn && this.filterTags.length ) {
      const has = new Set( ( item.tags || [] ).map( ( tag ) => tag.toLowerCase() ) );
      const hits = this.filterTags.filter( ( tag ) => has.has( tag.toLowerCase() ) ).length;
      if ( this.match === "any" && hits === 0 ) return false;
      if ( this.match === "all" && hits < this.filterTags.length ) return false;
      if ( this.match === "none" && hits > 0 ) return false;
    }
    const wanted = this.fold( this.text );
    if ( !wanted ) return true;
    const hay = [
      item.title , item.key , item.doi , item.journal , item.year ,
      ( item.tags || [] ).join( " " ) , Object.values( item.fields || {} ).join( " " ) ,
      ( ( paper && paper.authors ) || [] ).join( " " ) ,
    ].join( " " );
    return this.fold( hay ).includes( wanted );
  },

  describe() {
    const parts = [];
    if ( this.filterOn && this.filterTags.length ) {
      parts.push( I18n.get( "lists.filter_desc_" + this.match ).replace( "{tags}" , () => this.filterTags.join( ", " ) ) );
    }
    if ( this.fold( this.text ) ) parts.push( I18n.get( "lists.filter_desc_text" ).replace( "{text}" , () => this.text.trim() ) );
    return parts.join( " · " );
  },

  // The keys showing now, in order.
  shownKeys() {
    return Array.from( Dom.get( "list-rows" ).children ).map( ( row ) => row.getAttribute( "data-key" ) );
  },

  // ---- selection and painting ------------------------------------------------------

  selectedKeys() {
    const view = this.lists.view;
    if ( !view ) return [];
    return ( view.doc.items || [] ).map( ( item ) => item.key ).filter( ( key ) => this.selected.has( key ) );
  },

  onRowClick( event ) {
    const row = event.target.closest( "li.board-row" );
    if ( !row || event.target.closest( this.INTERACTIVE ) ) return;
    // A click that ends a text selection is reading, not picking.
    if ( !event.shiftKey && String( window.getSelection() || "" ).length > 0 ) return;
    const key = row.getAttribute( "data-key" );
    if ( this.armed && !this.lists.view.locked ) {
      const has = ( ( this.lists.row( key ) || {} ).tags || [] ).some( ( tag ) => tag.toLowerCase() === this.armed.toLowerCase() );
      if ( has ) this.lists.removeTag( [ key ] , this.armed );
      else this.lists.addTag( [ key ] , this.armed );
      return;
    }
    if ( event.metaKey || event.ctrlKey ) {
      if ( this.selected.has( key ) ) this.selected.delete( key );
      else this.selected.add( key );
      this.selAnchor = key;
    } else if ( event.shiftKey && this.selAnchor ) {
      const shown = this.shownKeys();
      const from = shown.indexOf( this.selAnchor );
      const to = shown.indexOf( key );
      if ( from >= 0 && to >= 0 ) {
        shown.slice( Math.min( from , to ) , Math.max( from , to ) + 1 ).forEach( ( each ) => this.selected.add( each ) );
      }
    } else if ( this.selected.size === 1 && this.selected.has( key ) ) {
      this.selected.clear();
    } else {
      this.selected = new Set( [ key ] );
      this.selAnchor = key;
    }
    this.paintSelection();
    this.drawBar();
  },

  paintSelection() {
    const rows = Dom.get( "list-rows" );
    for ( const key of Array.from( this.selected ) ) {
      if ( !this.lists.items.has( key ) ) this.selected.delete( key );
    }
    Array.from( rows.children ).forEach( ( row ) => {
      const on = this.selected.has( row.getAttribute( "data-key" ) );
      if ( row.classList.contains( "is-selected" ) !== on ) row.classList.toggle( "is-selected" , on );
      row.setAttribute( "aria-selected" , String( on ) );
    } );
    rows.classList.toggle( "is-painting" , Boolean( this.armed ) );
  },

  clearSelection() {
    this.selected.clear();
    this.selAnchor = null;
    this.paintSelection();
    this.drawBar();
  },

  unselect( key ) {
    this.selected.delete( key );
  },

  // ---- order, options -------------------------------------------------------------

  orderBy( by ) {
    return this.lists.changeWhole( "undo.list_order" , [ { op: "sort" , by: by } ] );
  },

  option( name , value ) {
    const options = this.lists.view.doc.options || {};
    const op = { op: "options" };
    op[ name ] = value;
    const back = { op: "options" };
    back[ name ] = name === "auto_move" ? Boolean( options[ name ] ) : ( options[ name ] || "bottom" );
    return this.lists.change( "undo.list_options" , [ op ] , [ back ] );
  },

  // ---- getting around -------------------------------------------------------------

  jump( n ) {
    const items = this.lists.view.doc.items || [];
    if ( !Number.isFinite( n ) || items.length === 0 ) return;
    const key = items[ Math.min( Math.max( n , 1 ) , items.length ) - 1 ].key;
    if ( !BoardView.flash( Dom.get( "list-rows" ) , key ) ) Dom.toast( I18n.get( "lists.hidden_by_filter" ) , "error" );
  },

  anchorKey() {
    return "list-anchor:" + this.lists.slug;
  },

  anchor() {
    if ( !this.lists.slug ) return null;
    const key = this.lists.local( this.anchorKey() );
    return key && this.lists.items.has( key ) ? key : null;
  },

  toggleAnchor( key ) {
    this.lists.local( this.anchorKey() , this.anchor() === key ? null : key );
    this.lists.draw();
  },
};
