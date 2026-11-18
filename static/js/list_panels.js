// The list menu and its dialogs: Columns, Tag colours, Citation style, Import
// references (onto the staging shelf), Import CSV, Export CSV, History (with
// restore), and View-only. Plus the shelf's own buttons. Each dialog sends ops
// like everything else, so each change is undoable and shows live elsewhere.

// One dialog for all of them: a title, a body and buttons, built fresh each
// time. open() answers when it closes.
const ListModal = {
  open( title , build ) {
    const element = Dom.get( "list-modal" );
    Dom.text( Dom.get( "list-modal-title" ) , title );
    this.problem( "" );
    this.refresh = () => {
      const parts = build();
      Dom.get( "list-modal-body" ).replaceChildren( ...( parts.body || [] ) );
      Dom.get( "list-modal-foot" ).replaceChildren( ...( parts.foot || [] ) );
      Dom.show( Dom.get( "list-modal-foot" ) , ( parts.foot || [] ).length > 0 );
    };
    this.refresh();
    const modal = bootstrap.Modal.getOrCreateInstance( element );
    return new Promise( ( resolve ) => {
      element.addEventListener( "hidden.bs.modal" , () => {
        this.refresh = null;
        resolve();
      } , { once: true } );
      modal.show();
    } );
  },

  close() {
    bootstrap.Modal.getOrCreateInstance( Dom.get( "list-modal" ) ).hide();
  },

  problem( text ) {
    Dom.text( Dom.get( "list-modal-problem" ) , text );
    Dom.show( Dom.get( "list-modal-problem" ) , Boolean( text ) );
  },

  // Redraws an open dialog after the list changed under it.
  redraw() {
    if ( this.refresh && Dom.get( "list-modal" ).classList.contains( "show" ) ) this.refresh();
  },
};

const ListPanels = {
  lists: null,

  init( lists ) {
    this.lists = lists;
    Dom.get( "list-shelf-all" ).addEventListener( "change" , ( event ) => {
      lists.checked = new Set( event.target.checked ? ( lists.view.doc.staging || [] ).map( ( item ) => item.key ) : [] );
      lists.draw();
    } );
    const tag = Dom.get( "list-shelf-tag" );
    tag.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      const name = tag.value.trim();
      const keys = Array.from( lists.checked );
      if ( !name || keys.length === 0 ) {
        if ( !keys.length ) Dom.toast( I18n.get( "lists.shelf_tick_first" ) , "error" );
        return;
      }
      tag.value = "";
      lists.addTag( keys , name );
    } );
    Dom.onPress( Dom.get( "list-shelf-drop" ) , () => {
      const keys = Array.from( lists.checked );
      if ( !keys.length ) return undefined;
      lists.checked.clear();
      return lists.changeWhole( "undo.list_shelf_drop" , [ { op: "stage_drop" , rows: keys } ] );
    } );
    Dom.onPress( Dom.get( "list-shelf-add" ) , () => this.addFromShelf() );
  },

  // ---- the menu -----------------------------------------------------------------

  drawMenu() {
    const view = this.lists.view;
    const locked = view.locked;
    const item = ( icon , key , run , options ) => {
      const settings = options || {};
      const button = Dom.el( "button" , {
        class: "dropdown-item" , attrs: { type: "button" },
        children: [ Dom.el( "i" , { class: "bi " + icon + " me-2" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: I18n.get( key ) } ) ],
        on: { click: run },
      } );
      if ( settings.check !== undefined ) {
        button.setAttribute( "role" , "menuitemcheckbox" );
        button.setAttribute( "aria-checked" , String( settings.check ) );
        if ( settings.check ) button.appendChild( Dom.el( "i" , { class: "bi bi-check-lg ms-2" , attrs: { "aria-hidden": "true" } } ) );
      }
      button.disabled = Boolean( settings.disabled );
      return Dom.el( "li" , { children: [ button ] } );
    };
    const rule = () => Dom.el( "li" , { children: [ Dom.el( "hr" , { class: "dropdown-divider" } ) ] } );
    const sync = ListManage.syncMode();
    const sig = JSON.stringify( [ view.slug , view.name , locked , sync , ( view.doc.sections || [] ).length > 0 ] );
    const menu = Dom.get( "list-menu-items" );
    if ( menu._sig === sig ) return;
    menu._sig = sig;
    const manage = ListManage;
    const shared = ( mode , key ) => {
      const entry = item( "bi-arrow-left-right" , key , () => manage.setSync( mode ) , { check: sync === mode , disabled: locked } );
      entry.firstChild.setAttribute( "role" , "menuitemradio" );
      return entry;
    };
    menu.replaceChildren(
      item( "bi-copy" , "lists.menu_duplicate" , () => manage.duplicate() ),
      item( "bi-pencil" , "lists.menu_rename" , () => manage.rename() ),
      item( "bi-link-45deg" , "lists.menu_link" , () => manage.link() ),
      item( "bi-trash" , "lists.menu_delete" , () => manage.remove() , { disabled: view.slug === "main" } ),
      rule(),
      Dom.el( "li" , { children: [ Dom.el( "h3" , { class: "dropdown-header" , text: I18n.get( "lists.menu_shared" ) } ) ] } ),
      shared( "two-way" , "lists.shared_two_way" ),
      shared( "one-way" , "lists.shared_one_way" ),
      shared( "off" , "lists.shared_off" ),
      rule(),
      item( "bi-bar-chart-steps" , "lists.menu_tiers" , () => manage.tiers() , { check: Boolean( ( view.doc.sections || [] ).length ) } ),
      item( "bi-palette" , "lists.menu_colours" , () => this.colours() , { disabled: locked } ),
      item( "bi-quote" , "lists.menu_cite" , () => this.citeStyle() , { disabled: locked } ),
      rule(),
      item( "bi-box-arrow-in-down" , "lists.menu_import" , () => manage.importFrom() , { disabled: locked } ),
      item( "bi-journal-arrow-down" , "lists.menu_refs" , () => this.importRefs() , { disabled: locked } ),
      item( "bi-filetype-csv" , "lists.menu_csv_import" , () => this.importCsv() , { disabled: locked } ),
      item( "bi-table" , "lists.menu_sheet" , () => ListSheet.open() , { disabled: locked } ),
      item( "bi-google" , "lists.menu_gsheet" , () => ListGSheet.open( view.slug ) ),
      item( "bi-download" , "lists.menu_csv_export" , () => this.exportCsv( false ) ),
      item( "bi-funnel" , "lists.menu_csv_export_shown" , () => this.exportCsv( true ) ),
      rule(),
      item( "bi-clock-history" , "lists.menu_history" , () => this.history() ),
      item( "bi-lock" , "lists.menu_lock" , () => this.lock( !locked ) , { check: locked } ),
      rule(),
      item( "bi-trash3" , "lists.menu_deleted" , () => manage.deleted() ),
    );
    ListModal.redraw();
  },

  // ---- view-only ----------------------------------------------------------------

  async lock( locked ) {
    const slug = this.lists.slug;
    const send = async ( value ) => {
      const answer = await Api.post( "/api/lists/" + encodeURIComponent( slug ) + "/lock" , { locked: value } );
      if ( slug === this.lists.slug ) {
        this.lists.view.locked = answer.list.locked;
        this.lists.draw();
      }
    };
    try {
      await Undo.run( {
        label: I18n.get( locked ? "undo.list_lock" : "undo.list_unlock" ),
        do: () => send( locked ),
        undo: () => send( !locked ),
      } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  // ---- columns --------------------------------------------------------------------

  // The board's Columns dropdown: the same picker as every table's (see
  // DataTable.drawMenu) -- tick to show, arrows to move -- and since a list's
  // columns are its own, each can also be renamed (pencil) or deleted, and new
  // ones added at the bottom. Unticked columns are hidden, for everyone who
  // opens the list. Drawn again whenever the list changes (ListTools.drawBar).
  columnsMenu( menu ) {
    const lists = this.lists;
    const doc = lists.view.doc;
    const locked = Boolean( lists.view.locked );
    const folded = new Set( ( doc.options && doc.options.fold_cols ) || [] );
    const cols = doc.columns || [];
    // Not while someone is typing in it: that would throw their text away.
    const sig = JSON.stringify( [ cols , [ ...folded ] , locked ] );
    if ( menu.contains( document.activeElement ) && document.activeElement.matches( "input[type=text]" ) ) return;
    if ( sig === this.columnsSig && menu.childElementCount ) return;
    this.columnsSig = sig;
    const run = async ( label , ops , back , whole ) => {
      try {
        if ( whole ) {
          const answer = await lists.changeWhole( label , ops , { toast: false } );
          if ( !answer ) throw new Error( I18n.get( "lists.columns_failed" ) );
        } else {
          await Undo.run( {
            label: I18n.get( label ),
            do: () => lists.send( lists.slug , ops ),
            undo: () => lists.send( lists.slug , back ),
          } );
        }
      } catch ( error ) {
        Dom.toast( error.message , "error" );
      }
    };
    const iconButton = ( icon , label , click , extra ) => Dom.el( "button" , {
      class: "btn btn-sm btn-link data-table-move" + ( extra || "" ),
      attrs: { type: "button" , title: label , "aria-label": label },
      children: [ Dom.el( "i" , { class: "bi bi-" + icon , attrs: { "aria-hidden": "true" } } ) ],
      on: { click: click },
    } );
    const items = [ Dom.el( "li" , { children: [ Dom.el( "h6" , { class: "dropdown-header" , text: I18n.get( "table.columns_heading" ) } ) ] } ) ];
    // The two the board always has, ticked and fixed, like Library's title.
    [ "lists.number_column" , "lists.paper_column" ].forEach( ( key ) => {
      const box = Dom.el( "input" , { class: "form-check-input mt-0" , attrs: { type: "checkbox" , "aria-label": I18n.get( key ) } } );
      box.checked = true;
      box.disabled = true;
      items.push( Dom.el( "li" , { children: [ Dom.el( "div" , {
        class: "dropdown-item-text d-flex align-items-center gap-2 data-table-menu-item",
        children: [ box , Dom.el( "span" , { class: "flex-grow-1 text-nowrap" , text: I18n.get( key ) } ) ],
      } ) ] } ) );
    } );
    cols.forEach( ( column , index ) => {
      const id = "list-col-" + column.id;
      const box = Dom.el( "input" , { class: "form-check-input mt-0" , attrs: { type: "checkbox" , id: id } } );
      box.checked = !folded.has( column.id );
      box.disabled = locked;
      box.addEventListener( "change" , () => run( "undo.list_columns" ,
        [ { op: "column_fold" , col: column.id , folded: !box.checked } ] ,
        [ { op: "column_fold" , col: column.id , folded: box.checked } ] ) );
      const label = Dom.el( "label" , { class: "form-check-label flex-grow-1 text-nowrap" , text: column.label , attrs: { for: id } } );
      const line = Dom.el( "div" , { class: "dropdown-item-text d-flex align-items-center gap-2 data-table-menu-item" } );
      const rename = () => {
        const name = Dom.el( "input" , { class: "form-control form-control-sm flex-grow-1" , attrs: { type: "text" , maxlength: "60" , "aria-label": I18n.get( "lists.column_name" ) } } );
        name.value = column.label;
        let finished = false;
        const finish = ( save ) => {
          if ( finished ) return;
          finished = true;
          const wanted = name.value.trim();
          this.columnsSig = "";
          if ( save && wanted && wanted !== column.label ) {
            run( "undo.list_columns" , [ { op: "column_rename" , col: column.id , label: wanted } ] , [ { op: "column_rename" , col: column.id , label: column.label } ] );
          } else {
            this.columnsMenu( menu );
          }
        };
        name.addEventListener( "keydown" , ( event ) => {
          if ( event.key === "Enter" ) {
            event.preventDefault();
            finish( true );
          } else if ( event.key === "Escape" ) {
            event.preventDefault();
            event.stopPropagation();
            finish( false );
          }
        } );
        name.addEventListener( "blur" , () => finish( true ) );
        label.replaceWith( name );
        name.focus();
        name.select();
      };
      const up = iconButton( "arrow-up" , I18n.get( "table.move_left" ) + ": " + column.label ,
        () => run( "undo.list_columns" , [ { op: "column_move" , col: column.id , to: index } ] , [ { op: "column_move" , col: column.id , to: index + 1 } ] ) );
      const down = iconButton( "arrow-down" , I18n.get( "table.move_right" ) + ": " + column.label ,
        () => run( "undo.list_columns" , [ { op: "column_move" , col: column.id , to: index + 2 } ] , [ { op: "column_move" , col: column.id , to: index + 1 } ] ) );
      up.disabled = locked || index === 0;
      down.disabled = locked || index === cols.length - 1;
      const pencil = iconButton( "pencil" , I18n.get( "lists.column_rename" ).replace( "{column}" , () => column.label ) , rename );
      const trash = iconButton( "trash" , I18n.get( "lists.column_delete" ).replace( "{column}" , () => column.label ) , async () => {
        const sure = await Dom.confirm( I18n.get( "lists.column_delete_confirm" ).replace( "{column}" , () => column.label ) );
        if ( sure ) await run( "undo.list_column_delete" , [ { op: "column_delete" , col: column.id } ] , null , true );
      } , " data-table-delete" );
      pencil.disabled = locked;
      trash.disabled = locked || cols.length <= 1;
      line.replaceChildren( box , label , pencil , up , down , trash );
      items.push( Dom.el( "li" , { children: [ line ] } ) );
    } );
    if ( !locked ) {
      items.push( Dom.el( "li" , { children: [ Dom.el( "hr" , { class: "dropdown-divider" } ) ] } ) );
      const fresh = Dom.el( "input" , { class: "form-control form-control-sm" , attrs: { type: "text" , maxlength: "60" , placeholder: I18n.get( "lists.column_new" ) , "aria-label": I18n.get( "lists.column_new" ) } } );
      const add = Dom.el( "button" , {
        class: "btn btn-sm btn-outline-primary" , attrs: { type: "button" },
        children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { class: "ms-1" , text: I18n.get( "lists.column_add" ) } ) ],
        on: { click: () => {
          const wanted = fresh.value.trim();
          if ( !wanted ) return undefined;
          fresh.value = "";
          this.columnsSig = "";
          return run( "undo.list_columns" , [ { op: "column_add" , label: wanted } ] , [ { op: "column_delete" , col: wanted } ] );
        } },
      } );
      fresh.addEventListener( "keydown" , ( event ) => {
        if ( event.key === "Enter" ) {
          event.preventDefault();
          add.click();
        }
      } );
      items.push( Dom.el( "li" , { children: [ Dom.el( "div" , { class: "dropdown-item-text" , children: [ Dom.el( "div" , { class: "input-group input-group-sm" , children: [ fresh , add ] } ) ] } ) ] } ) );
    }
    items.push( Dom.el( "li" , { children: [ Dom.el( "hr" , { class: "dropdown-divider" } ) ] } ) );
    items.push( Dom.el( "li" , { children: [ Dom.el( "button" , {
      class: "dropdown-item",
      attrs: { type: "button" },
      children: [ Dom.el( "i" , { class: "bi bi-arrow-counterclockwise me-2" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: I18n.get( "lists.reset_widths" ) } ) ],
      on: { click: () => {
        lists.local( "list-col-widths" , "{}" );
        lists.lastColSig = "";
        lists.draw();
      } },
    } ) ] } ) );
    menu.replaceChildren( ...items );
  },

  // ---- tag colours ---------------------------------------------------------------------

  colours() {
    const lists = this.lists;
    const set = ( name , color , previous ) => {
      ListModal.problem( "" );
      return lists.change( "undo.list_colour" , [ { op: "tag_color" , name: name , color: color } ] , [ { op: "tag_color" , name: name , color: previous } ] )
        .then( () => ListModal.redraw() );
    };
    ListModal.open( I18n.get( "lists.colours_title" ) , () => {
      const doc = lists.view.doc;
      const vocab = ( doc.vocab && doc.vocab.tags ) || [];
      const names = ListTools.tagNames();
      if ( names.length === 0 ) return { body: [ Dom.el( "p" , { class: "text-body-secondary" , text: I18n.get( "lists.colours_none" ) } ) ] };
      const rows = names.map( ( name ) => {
        const entry = vocab.find( ( tag ) => tag.name.toLowerCase() === name.toLowerCase() );
        const stored = ( entry && entry.color ) || "";
        const chip = TagColors.paint( Dom.el( "span" , { class: "tag-chip" , text: name } ) , name , vocab );
        // Shows the palette in use; stores the slot's WSU colour (TagColors).
        const storedSlot = stored ? TagColors.slot( stored ) : -1;
        const swatches = TagColors.palette.map( ( color , at ) => {
          const swatch = Dom.el( "button" , {
            class: "tag-swatch" + ( storedSlot === at ? " is-on" : "" ),
            attrs: { type: "button" , title: color , "aria-label": I18n.get( "lists.colour_pick" ).replace( "{tag}" , () => name ).replace( "{colour}" , color ) },
            on: { click: () => set( name , TagColors.wsu[ at ] , stored ) },
          } );
          swatch.style.backgroundColor = color;
          return swatch;
        } );
        const custom = Dom.el( "input" , { class: "form-control form-control-color form-control-sm" , attrs: { type: "color" , "aria-label": I18n.get( "lists.colour_custom" ).replace( "{tag}" , () => name ) } } );
        custom.value = TagColors.of( name , vocab );
        custom.addEventListener( "change" , () => set( name , custom.value.toLowerCase() , stored ) );
        const auto = Dom.el( "button" , {
          class: "btn btn-sm btn-link" , attrs: { type: "button" } , text: I18n.get( "lists.colour_auto" ),
          on: { click: () => set( name , "" , stored ) },
        } );
        auto.disabled = !stored;
        return Dom.el( "li" , { class: "list-group-item" , children: [
          Dom.el( "div" , { class: "d-flex flex-wrap align-items-center gap-2" , children: [ chip , Dom.el( "div" , { class: "tag-swatches" , children: swatches } ) , custom , auto ] } ),
        ] } );
      } );
      return { body: [ Dom.el( "ul" , { class: "list-group" , children: rows } ) ] };
    } );
  },

  // ---- citation style -------------------------------------------------------------------

  async citeStyle() {
    const lists = this.lists;
    let styles;
    try {
      styles = await Api.request( "/api/cite/styles" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    ListModal.open( I18n.get( "lists.cite_title" ) , () => {
      const own = ( lists.view.doc.options && lists.view.doc.options.cite_style ) || "";
      const choose = ( id ) => lists.change( "undo.list_options" , [ { op: "options" , cite_style: id } ] , [ { op: "options" , cite_style: own } ] )
        .then( () => {
          lists.cites = {};
          lists.fetchCites();
          ListModal.redraw();
        } );
      const option = ( id , title , ok , why ) => {
        const input = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "radio" , name: "list-cite-style" , id: "cite-" + ( id || "default" ) } } );
        input.checked = own === id;
        input.disabled = !ok;
        input.addEventListener( "change" , () => choose( id ) );
        const children = [ input , Dom.el( "label" , { class: "form-check-label" , text: title , attrs: { for: input.id } } ) ];
        if ( why ) children.push( Dom.el( "div" , { class: "form-text" , text: why } ) );
        return Dom.el( "div" , { class: "form-check mb-2" + ( ok ? "" : " text-body-secondary" ) , children: children } );
      };
      const fallback = styles.styles.find( ( style ) => style.id === styles.default );
      return { body: [
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.cite_help" ) } ),
        option( "" , I18n.get( "lists.cite_default" ).replace( "{style}" , () => ( fallback ? fallback.title : styles.default ) ) , true , "" ),
        ...styles.styles.map( ( style ) => option( style.id , style.title , style.ok , style.ok ? "" : style.why ) ),
      ] };
    } );
  },

  // ---- references onto the shelf ------------------------------------------------------------

  importRefs() {
    const lists = this.lists;
    let preview = null;
    let text = "";
    const area = Dom.el( "textarea" , { class: "form-control font-monospace small" , attrs: { rows: "10" , placeholder: I18n.get( "lists.refs_placeholder" ) , "aria-label": I18n.get( "lists.refs_paste" ) } } );
    const file = Dom.el( "input" , { class: "form-control" , attrs: { type: "file" , accept: ".docx,.txt,text/plain" , "aria-label": I18n.get( "lists.refs_file" ) } } );
    const readFile = () => new Promise( ( resolve , reject ) => {
      const reader = new FileReader();
      reader.onload = () => resolve( String( reader.result ).split( "," )[ 1 ] || "" );
      reader.onerror = () => reject( reader.error );
      reader.readAsDataURL( file.files[ 0 ] );
    } );
    const read = async () => {
      ListModal.problem( "" );
      try {
        const body = file.files.length ? { file: await readFile() } : { text: area.value };
        if ( !body.file && !area.value.trim() ) throw new Error( I18n.get( "lists.refs_nothing" ) );
        const answer = await Api.post( "/api/refs/parse" , body );
        preview = answer.refs;
        text = answer.text;
        if ( file.files.length ) area.value = text;
      } catch ( error ) {
        ListModal.problem( error.message );
      }
      ListModal.redraw();
    };
    const stage = async () => {
      ListModal.problem( "" );
      const answer = await lists.changeWhole( "undo.list_stage" , [ { op: "stage" , text: text || area.value } ] );
      if ( !answer ) return;
      const result = answer.results[ 0 ];
      Object.assign( lists.matched , result.matched || {} );
      lists.draw();
      ListModal.close();
      Dom.toast( I18n.get( "lists.refs_staged" ).replace( "{staged}" , result.staged ).replace( "{list}" , result.on_list ).replace( "{shelf}" , result.on_shelf ) , "ok" );
      Dom.movedOnPurpose();
      Dom.get( "list-shelf" ).scrollIntoView( { behavior: "smooth" , block: "start" } );
    };
    area.addEventListener( "input" , () => {
      preview = null;
      text = "";
    } );
    file.addEventListener( "change" , () => read() );
    ListModal.open( I18n.get( "lists.refs_title" ) , () => {
      const body = [
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.refs_help" ) } ),
        area,
        Dom.el( "div" , { class: "mt-2" , children: [ Dom.el( "label" , { class: "form-label small" , text: I18n.get( "lists.refs_file" ) } ) , file ] } ),
      ];
      const foot = [ Dom.el( "button" , { class: "btn btn-outline-secondary" , attrs: { type: "button" } , text: I18n.get( "lists.refs_check" ) , on: { click: () => read() } } ) ];
      if ( preview ) {
        const have = new Set( ( lists.view.doc.items || [] ).concat( lists.view.doc.staging || [] ).map( ( item ) => item.key.toLowerCase() ) );
        const fresh = preview.filter( ( ref ) => !have.has( ref.key.toLowerCase() ) );
        const found = preview.filter( ( ref ) => ref.in_library ).length;
        body.push( Dom.el( "p" , { class: "mt-3 mb-1 fw-semibold" , text: I18n.get( "lists.refs_preview" ).replace( "{read}" , preview.length ).replace( "{found}" , found ).replace( "{fresh}" , fresh.length ) } ) );
        body.push( Dom.el( "ol" , { class: "small refs-preview" , children: preview.slice( 0 , 200 ).map( ( ref ) => Dom.el( "li" , { children: [
          Dom.el( "span" , { text: ref.title || ref.raw } ),
          Dom.el( "span" , { class: "badge ms-2 " + ( ref.in_library ? "text-bg-success" : "text-bg-light border" ) , text: I18n.get( ref.in_library ? "lists.match_" + ( ref.matched || "library" ) : "lists.match_none_found" ) } ),
          have.has( ref.key.toLowerCase() ) ? Dom.el( "span" , { class: "badge ms-1 text-bg-secondary" , text: I18n.get( "lists.refs_already" ) } ) : document.createTextNode( "" ),
        ] } ) ) } ) );
        const go = Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.refs_stage" ).replace( "{count}" , fresh.length ) , on: { click: () => stage() } } );
        go.disabled = fresh.length === 0;
        foot.push( go );
      }
      return { body: body , foot: foot };
    } );
  },

  // Shelf -> list: the ticked rows, or all of them, where "Add to" says.
  addFromShelf() {
    const lists = this.lists;
    const staged = lists.view.doc.staging || [];
    const keys = lists.checked.size ? staged.map( ( item ) => item.key ).filter( ( key ) => lists.checked.has( key ) ) : staged.map( ( item ) => item.key );
    if ( keys.length === 0 ) return undefined;
    lists.checked.clear();
    return lists.changeWhole( "undo.list_shelf_add" , [ { op: "stage_add" , rows: keys } ] ).then( ( answer ) => {
      if ( answer ) BoardView.flash( Dom.get( "list-rows" ) , keys[ 0 ] );
    } );
  },

  // ---- CSV ---------------------------------------------------------------------------------

  async exportCsv( shownOnly ) {
    const lists = this.lists;
    const slug = lists.slug;
    const body = shownOnly && ListTools.filtering() ? { keys: ListTools.shownKeys() } : {};
    try {
      const response = await fetch( "/api/lists/" + encodeURIComponent( slug ) + "/export.csv" , {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify( Object.assign( { csrf_token: Api.csrfToken } , body ) ),
      } );
      if ( !response.ok ) throw new Error( ( await response.json().catch( () => ( {} ) ) ).error || response.statusText );
      const blob = await response.blob();
      const url = URL.createObjectURL( blob );
      const link = Dom.el( "a" , { attrs: { href: url , download: slug + ".csv" } } );
      document.body.appendChild( link );
      link.click();
      link.remove();
      setTimeout( () => URL.revokeObjectURL( url ) , 1000 );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  importCsv() {
    const lists = this.lists;
    let rows = null;
    let mode = "merge";
    let plan = null;
    const file = Dom.el( "input" , { class: "form-control" , attrs: { type: "file" , accept: ".csv,text/csv" , "aria-label": I18n.get( "lists.csv_file" ) } } );
    const replan = () => {
      ListModal.problem( "" );
      plan = null;
      if ( !rows ) return;
      try {
        plan = ListCSV.plan( rows , lists.view.doc , mode );
      } catch ( error ) {
        ListModal.problem( error.message );
      }
    };
    file.addEventListener( "change" , async () => {
      rows = null;
      if ( file.files.length ) {
        try {
          rows = ListCSV.parse( await file.files[ 0 ].text() );
        } catch ( error ) {
          ListModal.problem( error.message );
        }
      }
      replan();
      ListModal.redraw();
    } );
    const apply = async () => {
      ListModal.problem( "" );
      if ( !plan || plan.ops.length === 0 ) return;
      // Checked first, so a problem is named before anything changes.
      try {
        await Api.post( "/api/lists/" + encodeURIComponent( lists.slug ) + "/ops" , { ops: plan.ops , dry_run: true } );
      } catch ( error ) {
        ListModal.problem( error.message + ( error.payload && error.payload.index !== undefined ? " (" + JSON.stringify( error.payload.op ).slice( 0 , 160 ) + ")" : "" ) );
        return;
      }
      const answer = await lists.changeWhole( "undo.list_csv" , plan.ops );
      if ( answer ) ListModal.close();
    };
    ListModal.open( I18n.get( "lists.csv_title" ) , () => {
      const radio = ( value , key ) => {
        const input = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "radio" , name: "list-csv-mode" , id: "list-csv-" + value } } );
        input.checked = mode === value;
        input.addEventListener( "change" , () => {
          mode = value;
          replan();
          ListModal.redraw();
        } );
        return Dom.el( "div" , { class: "form-check" , children: [ input , Dom.el( "label" , { class: "form-check-label" , text: I18n.get( key ) , attrs: { for: input.id } } ) ] } );
      };
      const body = [
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.csv_help" ) } ),
        file,
        Dom.el( "fieldset" , { class: "mt-3" , children: [ radio( "merge" , "lists.csv_merge" ) , radio( "replace" , "lists.csv_replace" ) ] } ),
      ];
      const foot = [];
      if ( plan ) {
        const counts = plan.counts;
        let summary = I18n.get( "lists.csv_counts" ).replace( "{rows}" , plan.rows ).replace( "{new}" , counts.new ).replace( "{updated}" , counts.updated ).replace( "{unchanged}" , counts.unchanged );
        if ( mode === "replace" ) summary += " " + I18n.get( "lists.csv_removed" ).replace( "{removed}" , counts.removed );
        if ( plan.columns.length ) summary += " " + I18n.get( "lists.csv_new_columns" ).replace( "{columns}" , () => plan.columns.join( ", " ) );
        body.push( Dom.el( "p" , { class: "mt-3 fw-semibold" , text: summary } ) );
        const go = Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.csv_apply" ) , on: { click: () => apply() } } );
        go.disabled = plan.ops.length === 0;
        foot.push( go );
      }
      return { body: body , foot: foot };
    } );
  },

  // ---- history ---------------------------------------------------------------------------------

  async history() {
    const lists = this.lists;
    const slug = lists.slug;
    let versions = [];
    let picked = null;
    const load = async () => {
      const answer = await Api.request( "/api/lists/" + encodeURIComponent( slug ) + "/history?limit=1000" );
      versions = answer.versions;
    };
    try {
      await load();
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    const pick = async ( rev ) => {
      ListModal.problem( "" );
      try {
        const answer = await Api.request( "/api/lists/" + encodeURIComponent( slug ) + "/history/" + rev );
        picked = answer.version;
      } catch ( error ) {
        ListModal.problem( error.message );
      }
      ListModal.redraw();
    };
    const restore = async () => {
      if ( !picked ) return;
      const sure = await Dom.confirm( I18n.get( "lists.history_restore_confirm" ).replace( "{when}" , () => new Date( picked.at || 0 ).toLocaleString() ) );
      if ( !sure ) return;
      let before = null;
      const rev = picked.rev;
      try {
        await Undo.run( {
          label: I18n.get( "undo.list_restore" ),
          toast: true,
          do: async () => {
            before = lists.view.rev;
            await lists.restoreTo( slug , rev );
          },
          undo: () => lists.restoreTo( slug , before ),
        } );
        ListModal.close();
      } catch ( error ) {
        ListModal.problem( error.message );
      }
    };
    ListModal.open( I18n.get( "lists.history_title" ) , () => {
      if ( versions.length === 0 ) return { body: [ Dom.el( "p" , { class: "text-body-secondary" , text: I18n.get( "lists.history_none" ) } ) ] };
      const rows = versions.map( ( version ) => Dom.el( "button" , {
        class: "list-group-item list-group-item-action d-flex flex-wrap gap-2" + ( picked && picked.rev === version.rev ? " active" : "" ),
        attrs: { type: "button" },
        children: [
          Dom.when( version.at , "" ),
          Dom.el( "span" , { text: version.by || I18n.get( "lists.history_someone" ) } ),
          Dom.el( "span" , { class: "ms-auto small" , text: I18n.get( "lists.history_rows" ).replace( "{rows}" , version.rows ).replace( "{shelf}" , version.shelf ) } ),
        ],
        on: { click: () => pick( version.rev ) },
      } ) );
      const body = [
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.history_help" ) } ),
        Dom.el( "div" , { class: "list-group history-list" , children: rows } ),
      ];
      const foot = [];
      if ( picked ) {
        body.push( this.diffView( picked.doc , lists.view.doc ) );
        const go = Dom.el( "button" , { class: "btn btn-danger" , attrs: { type: "button" } , text: I18n.get( "lists.history_restore" ) , on: { click: () => restore() } } );
        go.disabled = lists.view.locked;
        foot.push( go );
      }
      return { body: body , foot: foot };
    } );
  },

  // A row's non-empty cells, in a fixed order.
  cellSig( item ) {
    return JSON.stringify( Object.entries( item.fields || {} ).filter( ( entry ) => entry[ 1 ] ).sort() );
  },

  // What restoring `older` would do to `now`: rows back, rows gone, moved, re-tagged, cells.
  diffView( older , now ) {
    const index = ( doc ) => new Map( ( doc.items || [] ).map( ( item , i ) => [ item.key , { item: item , at: i } ] ) );
    const was = index( older );
    const is = index( now );
    const back = [];
    const gone = [];
    let moved = 0;
    let tags = 0;
    let cells = 0;
    was.forEach( ( entry , key ) => {
      const current = is.get( key );
      if ( !current ) {
        back.push( entry.item );
        return;
      }
      if ( JSON.stringify( ( entry.item.tags || [] ).slice().sort() ) !== JSON.stringify( ( current.item.tags || [] ).slice().sort() ) ) tags += 1;
      if ( this.cellSig( entry.item ) !== this.cellSig( current.item ) ) cells += 1;
    } );
    is.forEach( ( entry , key ) => {
      if ( !was.has( key ) ) gone.push( entry.item );
    } );
    // Moved: common rows whose order differs.
    const common = ( older.items || [] ).map( ( item ) => item.key ).filter( ( key ) => is.has( key ) );
    const nowOrder = ( now.items || [] ).map( ( item ) => item.key ).filter( ( key ) => was.has( key ) );
    common.forEach( ( key , i ) => {
      if ( nowOrder[ i ] !== key ) moved += 1;
    } );
    const lines = [];
    const say = ( key , count ) => {
      if ( count ) lines.push( Dom.el( "li" , { text: I18n.get( key ).replace( "{count}" , count ) } ) );
    };
    say( "lists.diff_back" , back.length );
    say( "lists.diff_gone" , gone.length );
    say( "lists.diff_moved" , moved );
    say( "lists.diff_tags" , tags );
    say( "lists.diff_cells" , cells );
    const out = [ Dom.el( "h3" , { class: "h6 mt-3" , text: I18n.get( "lists.diff_title" ) } ) ];
    if ( lines.length === 0 ) {
      out.push( Dom.el( "p" , { class: "text-body-secondary" , text: I18n.get( "lists.diff_same_rows" ) } ) );
    } else {
      out.push( Dom.el( "ul" , { children: lines } ) );
    }
    const titles = ( key , items ) => {
      if ( !items.length ) return;
      out.push( Dom.el( "div" , { class: "small fw-semibold" , text: I18n.get( key ) } ) );
      out.push( Dom.el( "ul" , { class: "small" , children: items.slice( 0 , 12 ).map( ( item ) => Dom.el( "li" , { text: item.title || item.key } ) ).concat(
        items.length > 12 ? [ Dom.el( "li" , { class: "text-body-secondary" , text: I18n.get( "lists.diff_more" ).replace( "{count}" , items.length - 12 ) } ) ] : [] ) } ) );
    };
    titles( "lists.diff_back_titles" , back );
    titles( "lists.diff_gone_titles" , gone );
    return Dom.el( "div" , { children: out } );
  },
};
