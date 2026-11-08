// Draws a list's rows, and turns what someone does to a row into a call to
// the handlers lists.js passes in. It holds no state of its own and never
// talks to the server: lists.js owns the document, sends the ops and redraws.
//
// A row: its number (type another and press Enter to move it there), a grip
// to drag it by, the title, authors · year · journal, the paper's links, its
// tags (× removes one, the box adds one), its notes, and a remove button.
//
// handlers: { move( key , position ) , moveNear( key , anchorKey , side ) ,
//             remove( key ) , addTag( key , name ) , removeTag( key , name ) ,
//             setNote( key , value ) }
const BoardView = {
  dragging: null,

  // container is the <ol>. doc the list document, papers what the library
  // knows of each row, filter the text box's value, locked for a view-only
  // list. Answers how many rows are showing.
  render( container , doc , papers , handlers , filter , locked ) {
    const notes = ( doc.columns || [] ).find( ( column ) => column.id === "notes" );
    const wanted = this.fold( filter );
    const rows = [];
    ( doc.items || [] ).forEach( ( item , index ) => {
      if ( wanted && !this.matches( item , papers[ item.key ] , wanted ) ) return;
      rows.push( this.row( item , index + 1 , doc , papers[ item.key ] || {} , handlers , notes , locked ) );
    } );
    container.replaceChildren( ...rows );
    return rows.length;
  },

  fold( text ) {
    return String( text || "" ).normalize( "NFKD" ).replace( /[̀-ͯ]/g , "" ).toLowerCase().trim();
  },

  matches( item , paper , wanted ) {
    const hay = [
      item.title , item.key , item.doi , item.journal , item.year ,
      ( item.tags || [] ).join( " " ) , Object.values( item.fields || {} ).join( " " ) ,
      ( ( paper && paper.authors ) || [] ).join( " " ) ,
    ].join( " " );
    return this.fold( hay ).includes( wanted );
  },

  label( key , title ) {
    return I18n.get( key ).replace( "{title}" , () => title || "" );
  },

  row( item , position , doc , paper , handlers , notes , locked ) {
    const li = Dom.el( "li" , { class: "board-row" , attrs: { "data-key": item.key } } );

    const number = Dom.el( "input" , {
      class: "form-control form-control-sm board-row-num",
      attrs: { type: "text" , inputmode: "numeric" , value: String( position ) , "aria-label": this.label( "lists.position_label" , item.title ) },
    } );
    number.disabled = locked;
    const commit = () => {
      const wanted = parseInt( number.value , 10 );
      if ( !Number.isFinite( wanted ) || wanted === position ) {
        number.value = String( position );
        return;
      }
      handlers.move( item.key , wanted );
    };
    number.addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Enter" ) {
        event.preventDefault();
        commit();
      } else if ( event.key === "Escape" ) {
        number.value = String( position );
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

    const meta = PaperLinks.meta( { authors: paper.authors || [] , year: item.year , journal: item.journal } , paper.n_authors );
    const foot = [ PaperLinks.strip( { key: item.key , doi: item.doi , has_pdf: paper.has_pdf } ) ];
    if ( paper.in_library === false ) {
      foot.push( Dom.el( "span" , { class: "badge text-bg-light border" , text: I18n.get( "lists.not_in_library" ) } ) );
    }

    const main = Dom.el( "div" , {
      class: "board-row-main",
      children: [
        Dom.el( "div" , { class: "paper-title" , text: item.title || item.key } ),
        Dom.el( "div" , { class: "paper-meta" , text: meta } ),
        Dom.el( "div" , { class: "paper-foot" , children: foot } ),
        this.tags( item , doc , handlers , locked ),
      ],
    } );
    if ( notes ) main.appendChild( this.note( item , notes , handlers , locked ) );

    const remove = Dom.el( "button" , {
      class: "btn btn-sm btn-link board-row-remove",
      attrs: { type: "button" , title: I18n.get( "lists.remove" ) , "aria-label": I18n.get( "lists.remove" ) },
      children: [ Dom.el( "i" , { class: "bi bi-x-lg" , attrs: { "aria-hidden": "true" } } ) ],
      on: { click: () => handlers.remove( item.key ) },
    } );
    remove.hidden = locked;

    li.append( Dom.el( "div" , { class: "board-row-side" , children: [ number , grip ] } ) , main , remove );
    return li;
  },

  tags( item , doc , handlers , locked ) {
    const vocab = ( doc.vocab && doc.vocab.tags ) || [];
    const chips = ( item.tags || [] ).map( ( name ) => {
      const chip = Dom.el( "span" , { class: "tag-chip" , children: [ Dom.el( "span" , { text: name } ) ] } );
      TagColors.paint( chip , name , vocab );
      if ( !locked ) {
        chip.appendChild( Dom.el( "button" , {
          class: "tag-chip-remove",
          attrs: { type: "button" , "aria-label": I18n.get( "lists.tag_remove" ).replace( "{tag}" , () => name ) },
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

  note( item , column , handlers , locked ) {
    const value = ( item.fields || {} )[ column.id ] || "";
    const area = Dom.el( "textarea" , {
      class: "form-control form-control-sm board-row-note",
      attrs: { rows: "1" , placeholder: I18n.get( "lists.notes_placeholder" ) , "aria-label": this.label( "lists.notes_label" , item.title ) },
    } );
    area.value = value;
    area.readOnly = locked;
    // Tall enough for what is in it, from its line count: measuring each
    // box's scrollHeight would force a layout per row, which on a list of a
    // thousand rows is seconds. style.css adds field-sizing where browsers
    // have it, which also follows long lines that wrap.
    const fit = () => {
      area.rows = Math.min( 12 , Math.max( 1 , area.value.split( "\n" ).length ) );
    };
    area.addEventListener( "input" , fit );
    fit();
    area.addEventListener( "change" , () => {
      if ( area.value !== value ) handlers.setNote( item.key , area.value , value );
    } );
    return area;
  },

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
    const row = Array.from( container.children ).find( ( element ) => element.getAttribute( "data-key" ) === key );
    if ( !row ) return;
    row.scrollIntoView( { block: "nearest" , behavior: "smooth" } );
    row.classList.remove( "is-flashing" );
    void row.offsetWidth;
    row.classList.add( "is-flashing" );
  },
};
