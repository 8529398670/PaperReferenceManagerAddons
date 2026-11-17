// Draws a list's rows, and turns what someone does to a row into a call to the
// handlers lists.js passes in. It never talks to the server: lists.js owns the
// document, sends the ops, and calls render() again with the answer.
//
// Redrawing is KEYED. Each row element is kept with a signature of everything
// it shows; a new render reuses the element of every row whose signature did
// not change, rebuilds only the ones that did, and moves elements only where
// the order changed. A change to one row of a 1,500-row list touches one row,
// and the focus and the caret of everything else stay where they were.
//
// A row: its number (type another and Enter moves it there), a grip to drag
// it by, an anchor, the paper (title, authors · year · journal, its links, its
// citation with copy buttons, its tags), one cell per shown column, and a
// remove button. A cell is plain text in which any URL is a live link; click
// the words and it turns into a text box with the caret where you clicked.
//
// handlers: { move( key , position ) , moveNear( key , anchorKey , side ) ,
//             remove( key ) , addTag( key , name ) , removeTag( key , name ) ,
//             setCell( key , columnId , value , previous ) , rowClick( key , event ) ,
//             anchor( key ) , copy( text ) , rename( key , title , previous ) }
const BoardView = {
  dragging: null,
  // container -> { rows: Map( key -> { li , sig } ) }
  caches: new WeakMap(),
  URL_RE: /\bhttps?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]}]/g,

  // ctx: { doc , papers , handlers , locked , columns ( shown, in order ) ,
  //        visible ( keys to show, in order ) , positions ( key -> 1-based ) ,
  //        cites ( key -> { intext , full } ) , anchor , shelf ( bool ) ,
  //        matched ( key -> how a staged ref matched ) , checked ( Set ) }
  render( container , ctx ) {
    let cache = this.caches.get( container );
    if ( !cache ) {
      cache = { rows: new Map() };
      this.caches.set( container , cache );
    }
    const focus = this.focusOf( container );
    const vocab = ( ctx.doc.vocab && ctx.doc.vocab.tags ) || [];
    const colSig = ctx.columns.map( ( column ) => column.id + "=" + column.label ).join( "|" );
    const seen = new Set();
    const wanted = [];
    let rebuilt = 0;
    ctx.visible.forEach( ( key ) => {
      const item = ctx.items.get( key );
      if ( !item ) return;
      seen.add( key );
      const paper = ctx.papers[ key ] || {};
      const cite = ( ctx.cites && ctx.cites[ key ] ) || null;
      const tagColors = ( item.tags || [] ).map( ( name ) => TagColors.of( name , vocab ) ).join( "," );
      const sig = JSON.stringify( [ item , paper , cite , tagColors , colSig , ctx.locked , ctx.anchor === key ,
        ctx.shelf ? ( ctx.matched && ctx.matched[ key ] ) || "" : "" ] );
      let entry = cache.rows.get( key );
      if ( !entry || entry.sig !== sig ) {
        const li = ctx.shelf ? this.shelfRow( item , ctx , paper ) : this.row( item , ctx , paper , cite );
        entry = { li: li , sig: sig };
        cache.rows.set( key , entry );
        rebuilt += 1;
      }
      if ( !ctx.shelf ) {
        const number = entry.li.querySelector( ".board-row-num" );
        const position = String( ctx.positions.get( key ) );
        if ( number && number.value !== position && document.activeElement !== number ) number.value = position;
        number._position = ctx.positions.get( key );
      } else {
        const box = entry.li.querySelector( ".board-row-check" );
        if ( box ) box.checked = ctx.checked.has( key );
      }
      wanted.push( entry.li );
    } );
    for ( const key of Array.from( cache.rows.keys() ) ) {
      if ( !seen.has( key ) && !ctx.items.has( key ) ) cache.rows.delete( key );
    }
    this.place( container , wanted );
    this.restoreFocus( container , focus );
    return { shown: wanted.length , rebuilt: rebuilt };
  },

  // Puts container's children in the order of wanted, moving only what is out
  // of place, and taking out the rest.
  place( container , wanted ) {
    const keep = new Set( wanted );
    Array.from( container.children ).forEach( ( child ) => {
      if ( !keep.has( child ) ) child.remove();
    } );
    let cursor = container.firstElementChild;
    wanted.forEach( ( li ) => {
      if ( li === cursor ) {
        cursor = cursor.nextElementSibling;
      } else {
        container.insertBefore( li , cursor );
      }
    } );
  },

  // Forgets every kept row, so the next render rebuilds them all (the columns
  // or the language changed).
  reset( container ) {
    this.caches.delete( container );
    container.replaceChildren();
  },

  find( container , key ) {
    const cache = this.caches.get( container );
    const entry = cache && cache.rows.get( key );
    return entry && entry.li.isConnected ? entry.li : null;
  },

  // ---- focus: what had it gets it back after a rebuild ----------------------

  focusOf( container ) {
    const active = document.activeElement;
    if ( !active || !container.contains( active ) ) return null;
    const row = active.closest( "[data-key]" );
    const marked = active.closest( "[data-focus]" );
    if ( !row || !marked ) return null;
    // The row after it too: if this row goes (removed), the focus goes on to
    // the same place in the next one rather than back to the page.
    const after = row.nextElementSibling || row.previousElementSibling;
    const focus = {
      key: row.getAttribute( "data-key" ) , role: marked.getAttribute( "data-focus" ) , element: active ,
      next: after ? after.getAttribute( "data-key" ) : null,
    };
    if ( "value" in active && typeof active.value === "string" ) {
      focus.value = active.value;
      try {
        focus.start = active.selectionStart;
        focus.end = active.selectionEnd;
      } catch ( error ) { /* not every field has a caret */ }
    }
    return focus;
  },

  restoreFocus( container , focus ) {
    if ( !focus || focus.element.isConnected ) return;
    let row = this.find( container , focus.key );
    if ( !row && focus.next ) {
      row = this.find( container , focus.next );
      delete focus.value;
    }
    if ( !row ) return;
    const target = row.querySelector( '[data-focus="' + CSS.escape( focus.role ) + '"]' );
    if ( !target ) return;
    if ( target.classList.contains( "board-cell" ) && focus.value !== undefined ) {
      // It was being typed in: open it again, with what was typed.
      this.editCell( target , focus.value , focus.start , focus.end );
      return;
    }
    if ( focus.value !== undefined && "value" in target && !target.classList.contains( "board-row-num" ) ) target.value = focus.value;
    target.focus( { preventScroll: true } );
    try {
      if ( focus.start != null ) target.setSelectionRange( focus.start , focus.end );
    } catch ( error ) { /* no caret */ }
  },

  // ---- the header --------------------------------------------------------------

  // The column labels over the rows, each with an edge to drag for its width.
  head( element , columns , widths , onResize ) {
    const cells = [
      Dom.el( "div" , { class: "board-head-cell board-cell-side" , text: "#" } ),
      Dom.el( "div" , { class: "board-head-cell board-cell-paper" , text: I18n.get( "lists.paper_column" ) } ),
    ];
    columns.forEach( ( column ) => {
      const handle = Dom.el( "span" , { class: "board-resize" , attrs: { title: I18n.get( "lists.resize_help" ) } } );
      this.resizable( handle , column.id , widths , onResize );
      cells.push( Dom.el( "div" , { class: "board-head-cell" , children: [ Dom.el( "span" , { text: column.label } ) , handle ] } ) );
    } );
    cells.push( Dom.el( "div" , { class: "board-head-cell" } ) );
    element.replaceChildren( ...cells );
  },

  resizable( handle , id , widths , onResize ) {
    handle.addEventListener( "pointerdown" , ( event ) => {
      event.preventDefault();
      const cell = handle.parentElement;
      const startX = event.clientX;
      const startWidth = cell.getBoundingClientRect().width;
      handle.setPointerCapture( event.pointerId );
      const moving = ( move ) => onResize( id , Math.max( 96 , Math.round( startWidth + move.clientX - startX ) ) , false );
      const done = () => {
        handle.removeEventListener( "pointermove" , moving );
        onResize( id , null , true );
      };
      handle.addEventListener( "pointermove" , moving );
      handle.addEventListener( "pointerup" , done , { once: true } );
      handle.addEventListener( "pointercancel" , done , { once: true } );
    } );
    handle.addEventListener( "dblclick" , () => onResize( id , 0 , true ) );
  },

  // ---- a row on the list ----------------------------------------------------------

  label( key , title ) {
    return I18n.get( key ).replace( "{title}" , () => title || "" );
  },

  row( item , ctx , paper , cite ) {
    const handlers = ctx.handlers;
    const locked = ctx.locked;
    const li = Dom.el( "li" , { class: "board-row" , attrs: { "data-key": item.key } } );

    const number = Dom.el( "input" , {
      class: "form-control form-control-sm board-row-num",
      attrs: { type: "text" , inputmode: "numeric" , "data-focus": "num" , "aria-label": this.label( "lists.position_label" , item.title ) },
    } );
    number.disabled = locked;
    const commit = () => {
      const wanted = parseInt( number.value , 10 );
      if ( !Number.isFinite( wanted ) || wanted === number._position ) {
        number.value = String( number._position );
        return;
      }
      handlers.move( item.key , wanted );
    };
    number.addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Enter" ) {
        event.preventDefault();
        commit();
      } else if ( event.key === "Escape" ) {
        number.value = String( number._position );
        number.blur();
      }
    } );
    number.addEventListener( "change" , commit );

    const grip = Dom.el( "span" , {
      class: "board-row-grip",
      attrs: { title: I18n.get( "lists.drag_label" ) , "aria-hidden": "true" },
      children: [ Dom.el( "i" , { class: "bi bi-grip-vertical" } ) ],
    } );
    if ( !locked ) this.draggable( li , grip , item.key , handlers );
    const anchored = ctx.anchor === item.key;
    const anchor = Dom.el( "button" , {
      class: "btn btn-sm btn-link board-row-anchor" + ( anchored ? " is-on" : "" ),
      attrs: {
        type: "button" , "data-focus": "anchor" , "aria-pressed": String( anchored ),
        title: I18n.get( anchored ? "lists.anchor_off" : "lists.anchor_on" ) , "aria-label": I18n.get( anchored ? "lists.anchor_off" : "lists.anchor_on" ),
      },
      children: [ Dom.el( "i" , { class: "bi bi-anchor" , attrs: { "aria-hidden": "true" } } ) ],
      on: { click: () => handlers.anchor( item.key ) },
    } );

    const side = Dom.el( "div" , { class: "board-cell-side" , children: [ number , grip , anchor ] } );
    const main = Dom.el( "div" , { class: "board-cell-paper" , children: this.paperBlock( item , ctx , paper , cite ) } );
    const cells = ctx.columns.map( ( column ) => this.cell( item , column , ctx ) );
    const remove = Dom.el( "button" , {
      class: "btn btn-sm btn-link board-row-remove",
      attrs: { type: "button" , "data-focus": "remove" , title: I18n.get( "lists.remove" ) , "aria-label": I18n.get( "lists.remove" ) },
      children: [ Dom.el( "i" , { class: "bi bi-x-lg" , attrs: { "aria-hidden": "true" } } ) ],
      on: { click: () => handlers.remove( item.key ) },
    } );
    remove.hidden = locked;
    li.append( side , main , ...cells , Dom.el( "div" , { class: "board-cell-end" , children: [ remove ] } ) );
    return li;
  },

  paperBlock( item , ctx , paper , cite ) {
    const meta = PaperLinks.meta( { authors: paper.authors || [] , year: item.year , journal: item.journal } , paper.n_authors );
    const foot = [ PaperLinks.strip( { key: item.key , doi: item.doi , has_pdf: paper.has_pdf } ) ];
    if ( paper.in_library === false ) {
      foot.push( Dom.el( "span" , { class: "badge text-bg-light border" , text: I18n.get( "lists.not_in_library" ) } ) );
    }
    const block = [
      Dom.el( "div" , { class: "paper-title" , text: item.title || item.key } ),
      Dom.el( "div" , { class: "paper-meta" , text: meta } ),
      Dom.el( "div" , { class: "paper-foot" , children: foot } ),
    ];
    if ( cite && cite.intext ) block.push( this.citeLine( cite , ctx.handlers ) );
    block.push( this.tags( item , ctx ) );
    return block;
  },

  citeLine( cite , handlers ) {
    const copy = ( role , labelKey , text ) => Dom.el( "button" , {
      class: "btn btn-link btn-sm p-0 board-copy",
      attrs: { type: "button" , "data-focus": role , title: I18n.get( labelKey + "_help" ) },
      text: I18n.get( labelKey ),
      on: { click: () => handlers.copy( text ) },
    } );
    return Dom.el( "div" , { class: "board-cite" , children: [
      Dom.el( "span" , { class: "board-cite-text" , text: cite.intext } ),
      copy( "copy-cite" , "lists.copy_cite" , cite.intext ),
      copy( "copy-ref" , "lists.copy_ref" , cite.full ),
    ] } );
  },

  tags( item , ctx ) {
    const handlers = ctx.handlers;
    const locked = ctx.locked;
    const vocab = ( ctx.doc.vocab && ctx.doc.vocab.tags ) || [];
    const chips = ( item.tags || [] ).map( ( name ) => {
      const chip = Dom.el( "span" , { class: "tag-chip" , children: [ Dom.el( "span" , { text: name } ) ] } );
      TagColors.paint( chip , name , vocab );
      if ( !locked ) {
        chip.appendChild( Dom.el( "button" , {
          class: "tag-chip-remove",
          attrs: { type: "button" , "data-focus": "untag:" + name , "aria-label": I18n.get( "lists.tag_remove" ).replace( "{tag}" , () => name ) },
          text: "×",
          on: { click: () => handlers.removeTag( item.key , name ) },
        } ) );
      }
      return chip;
    } );
    const box = Dom.el( "div" , { class: "board-row-tags" , children: chips } );
    if ( !locked ) {
      const input = Dom.el( "input" , {
        class: "form-control form-control-sm tag-input",
        attrs: {
          type: "text",
          list: "list-tag-options",
          autocomplete: "off",
          "data-focus": "tag",
          placeholder: I18n.get( "lists.tag_add_placeholder" ),
          "aria-label": this.label( "lists.tag_add_label" , item.title ),
        },
      } );
      input.addEventListener( "keydown" , ( event ) => {
        if ( event.key !== "Enter" ) return;
        event.preventDefault();
        const name = input.value.trim();
        input.value = "";
        if ( name ) handlers.addTag( item.key , name );
      } );
      // Picking from the browser's suggestion list fires input, not Enter.
      input.addEventListener( "input" , ( event ) => {
        if ( event.inputType === "insertReplacementText" || event.inputType === undefined ) {
          const name = input.value.trim();
          if ( vocab.some( ( tag ) => tag.name === name ) ) {
            input.value = "";
            handlers.addTag( item.key , name );
          }
        }
      } );
      box.appendChild( input );
    }
    return box;
  },

  // ---- cells: plain text, live links, edited in place ------------------------------

  // The cell as it reads: text, with every URL a link that opens in a
  // background tab. Clicking anywhere else in it edits it.
  cell( item , column , ctx ) {
    const value = ( item.fields || {} )[ column.id ] || "";
    const cell = Dom.el( "div" , {
      class: "board-cell" + ( value ? "" : " is-empty" ),
      attrs: {
        "data-focus": "cell:" + column.id,
        "data-col": column.id,
        role: "textbox",
        "aria-multiline": "true",
        "aria-readonly": String( ctx.locked ),
        "aria-label": I18n.get( "lists.cell_label" ).replace( "{column}" , () => column.label ).replace( "{title}" , () => item.title || "" ),
        tabindex: "0",
      },
    } );
    cell._value = value;
    cell._save = ( next ) => {
      if ( next !== cell._value ) ctx.handlers.setCell( item.key , column.id , next , cell._value );
    };
    cell._locked = ctx.locked;
    cell._label = column.label;
    this.fillCell( cell , value , column.label );
    cell.addEventListener( "click" , ( event ) => {
      if ( event.target.closest( "a" ) || cell._locked || cell.querySelector( "textarea" ) ) return;
      const offset = this.offsetAt( cell , event );
      this.editCell( cell , cell._value , offset , offset );
    } );
    cell.addEventListener( "keydown" , ( event ) => {
      if ( event.target !== cell || cell._locked ) return;
      if ( event.key === "Enter" || ( event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey ) ) {
        event.preventDefault();
        const end = cell._value.length;
        this.editCell( cell , event.key === "Enter" ? cell._value : cell._value + event.key , end + ( event.key === "Enter" ? 0 : 1 ) );
      }
    } );
    return cell;
  },

  fillCell( cell , value , label ) {
    if ( !value ) {
      cell.replaceChildren( Dom.el( "span" , { class: "board-cell-placeholder" , text: label } ) );
      return;
    }
    const parts = [];
    let last = 0;
    value.replace( this.URL_RE , ( url , at ) => {
      if ( at > last ) parts.push( document.createTextNode( value.slice( last , at ) ) );
      parts.push( Dom.el( "a" , { text: url , attrs: { href: url , target: "_blank" , rel: "noopener noreferrer" } } ) );
      last = at + url.length;
      return url;
    } );
    if ( last < value.length ) parts.push( document.createTextNode( value.slice( last ) ) );
    cell.replaceChildren( ...parts );
  },

  // Where in the cell's text a click landed, so the caret goes there.
  offsetAt( cell , event ) {
    let node = null;
    let offset = 0;
    if ( document.caretPositionFromPoint ) {
      const position = document.caretPositionFromPoint( event.clientX , event.clientY );
      if ( position ) {
        node = position.offsetNode;
        offset = position.offset;
      }
    } else if ( document.caretRangeFromPoint ) {
      const range = document.caretRangeFromPoint( event.clientX , event.clientY );
      if ( range ) {
        node = range.startContainer;
        offset = range.startOffset;
      }
    }
    if ( !node || !cell.contains( node ) || cell.classList.contains( "is-empty" ) ) return cell._value.length;
    let total = 0;
    const walker = document.createTreeWalker( cell , NodeFilter.SHOW_TEXT );
    while ( walker.nextNode() ) {
      if ( walker.currentNode === node ) return total + offset;
      total += walker.currentNode.nodeValue.length;
    }
    return cell._value.length;
  },

  editCell( cell , value , start , end ) {
    if ( cell._locked ) return;
    const area = Dom.el( "textarea" , { class: "form-control form-control-sm board-cell-edit" , attrs: { rows: "1" , "aria-label": cell.getAttribute( "aria-label" ) } } );
    area.value = value;
    const fit = () => {
      area.rows = Math.min( 16 , Math.max( 1 , area.value.split( "\n" ).length ) );
    };
    fit();
    area.addEventListener( "input" , fit );
    let cancelled = false;
    area.addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Escape" ) {
        cancelled = true;
        event.stopPropagation();
        area.blur();
      } else if ( event.key === "Enter" && ( event.metaKey || event.ctrlKey ) ) {
        event.preventDefault();
        area.blur();
      }
    } );
    area.addEventListener( "blur" , () => {
      const next = area.value;
      if ( !cancelled && next !== cell._value ) {
        cell._save( next );
        cell._value = next;
      }
      cell.classList.toggle( "is-empty" , !cell._value );
      cell.setAttribute( "tabindex" , "0" );
      this.fillCell( cell , cell._value , cell._label );
    } );
    cell.setAttribute( "tabindex" , "-1" );
    cell.classList.remove( "is-empty" );
    cell.replaceChildren( area );
    area.focus( { preventScroll: true } );
    try {
      area.setSelectionRange( start == null ? value.length : start , end == null ? ( start == null ? value.length : start ) : end );
    } catch ( error ) { /* fine */ }
  },

  // ---- a row on the staging shelf -------------------------------------------------

  shelfRow( item , ctx , paper ) {
    const handlers = ctx.handlers;
    const li = Dom.el( "li" , { class: "board-row board-row-shelf" , attrs: { "data-key": item.key } } );
    const check = Dom.el( "input" , {
      class: "form-check-input board-row-check",
      attrs: { type: "checkbox" , "data-focus": "check" , "aria-label": this.label( "lists.shelf_check" , item.title ) },
    } );
    check.addEventListener( "change" , () => handlers.check( item.key , check.checked ) );
    const how = ( ctx.matched && ctx.matched[ item.key ] ) || "";
    const badge = paper.in_library
      ? I18n.get( how ? "lists.match_" + how : "lists.match_library" )
      : I18n.get( "lists.match_none_found" );
    const title = Dom.el( "input" , {
      class: "form-control form-control-sm board-shelf-title",
      attrs: { type: "text" , "data-focus": "title" , "aria-label": this.label( "lists.shelf_title" , item.title ) },
    } );
    title.value = item.title || "";
    title.readOnly = ctx.locked;
    title.addEventListener( "change" , () => {
      if ( title.value.trim() && title.value !== item.title ) handlers.rename( item.key , title.value.trim() , item.title || "" );
    } );
    const meta = PaperLinks.meta( { authors: paper.authors || ( item.authors ? [ item.authors ] : [] ) , year: item.year , journal: item.journal } , paper.n_authors );
    const main = Dom.el( "div" , { class: "board-cell-paper" , children: [
      title,
      Dom.el( "div" , { class: "paper-meta" , text: meta } ),
      Dom.el( "div" , { class: "paper-foot" , children: [
        PaperLinks.strip( { key: item.key , doi: item.doi , has_pdf: paper.has_pdf } ),
        Dom.el( "span" , { class: "badge border " + ( paper.in_library ? "text-bg-success" : "text-bg-light" ) , text: badge } ),
      ] } ),
      this.tags( item , ctx ),
    ] } );
    const cells = ctx.columns.map( ( column ) => this.cell( item , column , ctx ) );
    li.append( Dom.el( "div" , { class: "board-cell-side" , children: [ check ] } ) , main , ...cells , Dom.el( "div" , { class: "board-cell-end" } ) );
    return li;
  },

  // ---- dragging ---------------------------------------------------------------------

  // Drag by the grip only, so the text in a row can still be selected.
  draggable( li , grip , key , handlers ) {
    grip.addEventListener( "pointerdown" , () => { li.draggable = true; } );
    li.addEventListener( "dragstart" , ( event ) => {
      this.dragging = key;
      li.classList.add( "is-dragging" );
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData( "text/plain" , key );
    } );
    li.addEventListener( "dragend" , () => {
      li.draggable = false;
      li.classList.remove( "is-dragging" );
      this.dragging = null;
      Dom.all( ".drop-before, .drop-after" ).forEach( ( row ) => row.classList.remove( "drop-before" , "drop-after" ) );
    } );
    li.addEventListener( "dragover" , ( event ) => {
      if ( !this.dragging || this.dragging === key ) return;
      event.preventDefault();
      const box = li.getBoundingClientRect();
      const after = event.clientY > box.top + box.height / 2;
      li.classList.toggle( "drop-after" , after );
      li.classList.toggle( "drop-before" , !after );
    } );
    li.addEventListener( "dragleave" , () => li.classList.remove( "drop-before" , "drop-after" ) );
    li.addEventListener( "drop" , ( event ) => {
      event.preventDefault();
      const moving = this.dragging;
      const side = li.classList.contains( "drop-after" ) ? "after" : "before";
      li.classList.remove( "drop-before" , "drop-after" );
      if ( moving && moving !== key ) handlers.moveNear( moving , key , side );
    } );
  },

  // Brings a row into view and flashes it, after it was added or moved.
  flash( container , key ) {
    const row = this.find( container , key );
    if ( !row ) return false;
    Dom.movedOnPurpose();
    row.scrollIntoView( { block: "center" , behavior: "smooth" } );
    row.classList.remove( "is-flashing" );
    void row.offsetWidth;
    row.classList.add( "is-flashing" );
    return true;
  },
};
