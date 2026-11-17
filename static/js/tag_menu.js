// Right-click on any tag on the Lists screen (a chip in the tag bar, or a tag
// on a row) for a small menu: rename it, recolour it, delete it from the
// whole list, or take it off just that paper. The ContextMenu key (or
// Shift+F10) on a focused chip opens it too.
//
// Every tag drawn on the screen carries data-tag="<name>"; a row's tag sits
// inside its row's [data-key]. The menu is one Bootstrap .dropdown-menu, made
// once and placed at the pointer. A view-only list keeps the browser's own
// menu.
//
// Rename and delete reach every row, so their undo is the version from just
// before (changeWhole); a colour change undoes op by op.
const TagMenu = {
  lists: null,
  menu: null,
  name: "",
  rowKey: null,
  returnTo: null,

  init( lists ) {
    this.lists = lists;
    this.menu = Dom.el( "div" , { class: "dropdown-menu shadow tag-menu" , attrs: { role: "menu" , tabindex: "-1" } } );
    document.body.appendChild( this.menu );
    Dom.get( "lists-panel" ).addEventListener( "contextmenu" , ( event ) => {
      const chip = event.target.closest( "[data-tag]" );
      if ( !chip || !this.lists.view || this.lists.view.locked ) return;
      event.preventDefault();
      const row = chip.closest( "[data-key]" );
      let x = event.clientX;
      let y = event.clientY;
      // From the keyboard there is no pointer: open under the chip.
      if ( !x && !y ) {
        const box = chip.getBoundingClientRect();
        x = box.left;
        y = box.bottom;
      }
      this.open( chip.getAttribute( "data-tag" ) , row && row.closest( "#list-rows" ) ? row.getAttribute( "data-key" ) : null , x , y );
    } );
    document.addEventListener( "pointerdown" , ( event ) => {
      // A right-click on another tag opens the menu there instead.
      if ( event.button === 2 && event.target.closest( "[data-tag]" ) ) return;
      if ( this.isOpen() && !this.menu.contains( event.target ) ) this.close( false );
    } , true );
    document.addEventListener( "keydown" , ( event ) => {
      if ( !this.isOpen() ) return;
      if ( event.key === "Escape" ) {
        event.preventDefault();
        event.stopPropagation();
        this.close( true );
      } else if ( event.key === "ArrowDown" || event.key === "ArrowUp" ) {
        event.preventDefault();
        this.step( event.key === "ArrowDown" ? 1 : -1 );
      }
    } , true );
    // It belongs to a spot on the screen; once that moves, it goes.
    window.addEventListener( "resize" , () => this.close( false ) );
    document.addEventListener( "scroll" , ( event ) => {
      if ( this.isOpen() && !this.menu.contains( event.target ) ) this.close( false );
    } , { capture: true , passive: true } );
  },

  isOpen() {
    return this.menu.classList.contains( "show" );
  },

  close( refocus ) {
    if ( !this.isOpen() ) return;
    this.menu.classList.remove( "show" );
    if ( refocus && this.returnTo && this.returnTo.isConnected ) this.returnTo.focus( { preventScroll: true } );
  },

  step( by ) {
    const items = Array.from( this.menu.querySelectorAll( ".dropdown-item:not(:disabled), .tag-swatch, input" ) );
    if ( !items.length ) return;
    const at = items.indexOf( document.activeElement );
    items[ ( at + by + items.length ) % items.length ].focus();
  },

  // How many rows of the list (and the shelf) carry the tag.
  uses( name ) {
    const lower = name.toLowerCase();
    const doc = this.lists.view.doc;
    return ( doc.items || [] ).concat( doc.staging || [] )
      .filter( ( item ) => ( item.tags || [] ).some( ( tag ) => tag.toLowerCase() === lower ) ).length;
  },

  open( name , rowKey , x , y ) {
    this.name = name;
    this.rowKey = rowKey;
    this.returnTo = document.activeElement;
    this.draw();
    const menu = this.menu;
    menu.style.left = "0px";
    menu.style.top = "0px";
    menu.classList.add( "show" );
    // Kept on screen: flipped left or up when it would run off an edge.
    const box = menu.getBoundingClientRect();
    const left = x + box.width > window.innerWidth - 8 ? Math.max( 8 , x - box.width ) : x;
    const top = y + box.height > window.innerHeight - 8 ? Math.max( 8 , y - box.height ) : y;
    menu.style.left = Math.round( left ) + "px";
    menu.style.top = Math.round( top ) + "px";
    const first = menu.querySelector( ".dropdown-item" );
    if ( first ) first.focus( { preventScroll: true } );
  },

  item( icon , key , run , tone ) {
    return Dom.el( "button" , {
      class: "dropdown-item d-flex align-items-center gap-2" + ( tone ? " text-" + tone : "" ),
      attrs: { type: "button" , role: "menuitem" },
      children: [ Dom.el( "i" , { class: "bi " + icon , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: I18n.get( key ) } ) ],
      on: { click: () => {
        this.close( true );
        return run();
      } },
    } );
  },

  draw() {
    const name = this.name;
    const lists = this.lists;
    const vocab = ( lists.view.doc.vocab && lists.view.doc.vocab.tags ) || [];
    const entry = lists.vocabEntry( name );
    const stored = ( entry && entry.color ) || "";
    const storedSlot = stored ? TagColors.slot( stored ) : -1;
    const n = this.uses( name );
    const head = Dom.el( "div" , { class: "dropdown-header d-flex align-items-center gap-2" , children: [
      TagColors.paint( Dom.el( "span" , { class: "tag-chip" , text: name } ) , name , vocab ),
      Dom.el( "span" , { class: "small" , text: I18n.get( n === 1 ? "lists.tag_menu_uses_one" : "lists.tag_menu_uses" ).replace( "{count}" , n.toLocaleString() ) } ),
    ] } );

    const recolour = ( color ) => {
      this.close( true );
      if ( color === stored ) return;
      return lists.change( "undo.list_colour" , [ { op: "tag_color" , name: name , color: color } ] , [ { op: "tag_color" , name: name , color: stored } ] );
    };
    const swatches = TagColors.palette.map( ( color , at ) => {
      const swatch = Dom.el( "button" , {
        class: "tag-swatch" + ( storedSlot === at ? " is-on" : "" ),
        attrs: { type: "button" , title: color , "aria-label": I18n.get( "lists.colour_pick" ).replace( "{tag}" , () => name ).replace( "{colour}" , color ) },
        on: { click: () => recolour( TagColors.wsu[ at ] ) },
      } );
      swatch.style.backgroundColor = color;
      return swatch;
    } );
    const custom = Dom.el( "input" , {
      class: "form-control form-control-color form-control-sm tag-menu-custom",
      attrs: { type: "color" , title: I18n.get( "lists.colour_custom" ).replace( "{tag}" , () => name ) , "aria-label": I18n.get( "lists.colour_custom" ).replace( "{tag}" , () => name ) },
    } );
    custom.value = TagColors.of( name , vocab );
    custom.addEventListener( "change" , () => recolour( custom.value.toLowerCase() ) );
    const auto = Dom.el( "button" , {
      class: "btn btn-sm btn-link px-1" , attrs: { type: "button" } , text: I18n.get( "lists.colour_auto" ),
      on: { click: () => recolour( "" ) },
    } );
    auto.disabled = !stored;
    const colours = Dom.el( "div" , { class: "px-3 py-1" , children: [
      Dom.el( "div" , { class: "small text-body-secondary mb-1" , text: I18n.get( "lists.tag_menu_colour" ) } ),
      Dom.el( "div" , { class: "tag-swatches" , children: swatches } ),
      Dom.el( "div" , { class: "d-flex align-items-center gap-2 mt-2" , children: [ custom , auto ] } ),
    ] } );

    const parts = [ head , this.item( "bi-pencil" , "lists.tag_menu_rename" , () => this.rename() ) ];
    if ( this.rowKey ) {
      parts.push( this.item( "bi-x-circle" , "lists.tag_menu_untag" , () => lists.removeTag( [ this.rowKey ] , name ) ) );
    }
    parts.push(
      Dom.el( "hr" , { class: "dropdown-divider" } ),
      colours,
      Dom.el( "hr" , { class: "dropdown-divider" } ),
      this.item( "bi-trash" , "lists.tag_menu_delete" , () => this.remove() , "danger" ),
    );
    this.menu.replaceChildren( ...parts );
  },

  rename() {
    const lists = this.lists;
    const from = this.name;
    const input = Dom.el( "input" , { class: "form-control" , attrs: { type: "text" , maxlength: "60" , autocomplete: "off" , "aria-label": I18n.get( "lists.tag_menu_new_name" ) } } );
    input.value = from;
    const save = async () => {
      const to = input.value.trim();
      if ( !to || to === from ) {
        ListModal.close();
        return;
      }
      const other = lists.vocabEntry( to );
      if ( other && other.name.toLowerCase() !== from.toLowerCase() ) {
        const merge = await Dom.confirm( I18n.get( "lists.tag_menu_merge_confirm" ).replace( "{from}" , () => from ).replace( "{to}" , () => other.name ) );
        if ( !merge ) return;
      }
      ListModal.close();
      // A filter or a paint on the old name follows it.
      const same = ( tag ) => tag.toLowerCase() === from.toLowerCase();
      ListTools.filterTags = ListTools.filterTags.map( ( tag ) => ( same( tag ) ? to : tag ) );
      if ( ListTools.armed && same( ListTools.armed ) ) ListTools.armed = to;
      return lists.changeWhole( "undo.list_tag_rename" , [ { op: "tag_rename" , from: from , to: to } ] , { toast: false } );
    };
    input.addEventListener( "keydown" , ( event ) => {
      if ( event.key !== "Enter" ) return;
      event.preventDefault();
      save();
    } );
    ListModal.open( I18n.get( "lists.tag_menu_rename_title" ).replace( "{tag}" , () => from ) , () => ( {
      body: [ Dom.el( "label" , { class: "form-label" , text: I18n.get( "lists.tag_menu_new_name" ) } ) , input ],
      foot: [
        Dom.el( "button" , { class: "btn btn-outline-secondary" , attrs: { type: "button" , "data-bs-dismiss": "modal" } , text: I18n.get( "lists.tag_menu_cancel" ) } ),
        Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.tag_menu_rename_save" ) , on: { click: save } } ),
      ],
    } ) );
    Dom.get( "list-modal" ).addEventListener( "shown.bs.modal" , () => {
      input.focus();
      input.select();
    } , { once: true } );
  },

  async remove() {
    const name = this.name;
    const n = this.uses( name );
    const sure = await Dom.confirm( I18n.get( n ? "lists.tag_menu_delete_confirm" : "lists.tag_menu_delete_confirm_unused" ).replace( "{tag}" , () => name ).replace( "{count}" , n.toLocaleString() ) );
    if ( !sure ) return;
    // A filter or a paint on a tag that is gone would match nothing.
    const tools = ListTools;
    tools.filterTags = tools.filterTags.filter( ( tag ) => tag.toLowerCase() !== name.toLowerCase() );
    if ( tools.armed && tools.armed.toLowerCase() === name.toLowerCase() ) tools.armed = null;
    return this.lists.changeWhole( "undo.list_tag_delete" , [ { op: "tag_delete" , name: name } ] );
  },
};
