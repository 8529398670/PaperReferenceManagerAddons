// The lists themselves, rather than what is on them: duplicate, rename,
// delete (to the trash, undoable) and put back; links to one list
// (#lists/<slug>); how a list shares tag and cell edits with the others; and
// moving rows between lists (Copy to list…, Import from lists…).
//
// A list's lifecycle is not an op (ops change what is ON a list), so these
// call their own routes, each through Undo.run like everything else: creating
// a list is undone by deleting it, deleting by putting it back.
const ListManage = {
  lists: null,

  init( lists ) {
    this.lists = lists;
    window.addEventListener( "hashchange" , () => this.fromHash() );
    Dom.onPress( Dom.get( "list-copy-to" ) , () => this.copyTo() );
  },

  url( slug , tail ) {
    return "/api/lists/" + encodeURIComponent( slug ) + ( tail || "" );
  },

  // ---- links: #lists/<slug> ---------------------------------------------------------

  hashSlug() {
    const match = window.location.hash.match( /^#lists\/(.+)$/ );
    if ( !match ) return null;
    try {
      return decodeURIComponent( match[ 1 ] );
    } catch ( error ) {
      return null;
    }
  },

  // While the Lists screen is showing, the address names the open list, so it
  // can be copied, bookmarked or reloaded. replaceState: switching lists is
  // not a browser history step.
  showInHash( slug ) {
    if ( !/^#lists(\/|$)/.test( window.location.hash ) ) return;
    const want = "#lists/" + encodeURIComponent( slug );
    if ( window.location.hash !== want ) window.history.replaceState( null , "" , want );
  },

  fromHash() {
    const slug = this.hashSlug();
    if ( window.location.hash === "#lists" && this.lists.slug ) this.showInHash( this.lists.slug );
    if ( !slug || slug === this.lists.slug ) return;
    this.lists.open( slug ).catch( ( error ) => this.cannotOpen( error ) );
  },

  cannotOpen( error ) {
    Dom.toast( error.status === 410 ? I18n.get( "lists.list_gone" ) : error.message , "error" );
    if ( this.lists.slug ) this.showInHash( this.lists.slug );
  },

  link() {
    const slug = this.lists.slug;
    const text = window.location.origin + window.location.pathname + "#lists/" + encodeURIComponent( slug );
    this.lists.copy( text ).then( () => Dom.toast( I18n.get( "lists.link_copied" ) , "ok" ) ).catch( () => {} );
  },

  // ---- making, renaming, deleting -------------------------------------------------------

  // Makes a list (body as POST /api/lists takes it) and opens it. Undo puts it
  // in the trash; redo takes it out again rather than making a second one.
  async create( body , label ) {
    const lists = this.lists;
    const before = lists.slug;
    let made = null;
    try {
      await Undo.run( {
        label: I18n.get( label ),
        toast: true,
        do: async () => {
          if ( made ) await Api.post( this.url( made , "/undelete" ) , {} );
          else made = ( await Api.post( "/api/lists" , body ) ).list.slug;
          await lists.loadLists( made );
        },
        undo: async () => {
          await Api.post( this.url( made , "/delete" ) , {} );
          await lists.loadLists( before );
        },
      } );
      return made;
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return null;
    }
  },

  // A one-field dialog: a name, and a button that does something with it.
  nameDialog( title , help , value , go , run ) {
    const input = Dom.el( "input" , { class: "form-control" , attrs: { type: "text" , maxlength: "80" , id: "list-name-input" } } );
    input.value = value;
    const submit = async () => {
      const name = input.value.trim();
      if ( !name ) return;
      ListModal.problem( "" );
      try {
        await run( name );
        ListModal.close();
      } catch ( error ) {
        ListModal.problem( error.message );
      }
    };
    input.addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Enter" ) {
        event.preventDefault();
        submit();
      }
    } );
    Dom.get( "list-modal" ).addEventListener( "shown.bs.modal" , () => input.select() , { once: true } );
    ListModal.open( title , () => ( {
      body: [
        Dom.el( "label" , { class: "form-label" , text: I18n.get( "lists.name_label" ) , attrs: { for: "list-name-input" } } ),
        input,
        Dom.el( "p" , { class: "form-text mb-0" , text: help } ),
      ],
      foot: [ Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: go , on: { click: submit } } ) ],
    } ) );
  },

  duplicate() {
    const view = this.lists.view;
    this.nameDialog( I18n.get( "lists.duplicate_title" ) , I18n.get( "lists.duplicate_help" ) ,
      I18n.get( "lists.duplicate_name" ).replace( "{name}" , () => view.name ) , I18n.get( "lists.duplicate_go" ) ,
      async ( name ) => {
        const made = await this.create( { name: name , from: view.slug } , "undo.list_duplicate" );
        if ( !made ) throw new Error( I18n.get( "lists.columns_failed" ) );
      } );
  },

  rename() {
    const lists = this.lists;
    const view = lists.view;
    const help = I18n.get( view.slug === "main" ? "lists.rename_main_help" : "lists.rename_help" );
    this.nameDialog( I18n.get( "lists.rename_title" ) , help , view.name , I18n.get( "lists.rename_go" ) , async ( name ) => {
      if ( name === view.name ) return;
      let slug = view.slug;
      const send = async ( value ) => {
        const answer = await Api.post( this.url( slug , "/rename" ) , { name: value } );
        slug = answer.list.slug;
        await lists.loadLists( slug );
      };
      const old = view.name;
      await Undo.run( { label: I18n.get( "undo.list_rename" ) , do: () => send( name ) , undo: () => send( old ) } );
    } );
  },

  async remove() {
    const lists = this.lists;
    const slug = lists.slug;
    if ( slug === "main" ) return;
    try {
      await Undo.run( {
        label: I18n.get( "undo.list_delete" ),
        toast: true,
        do: async () => {
          await Api.post( this.url( slug , "/delete" ) , {} );
          await lists.loadLists( "main" );
        },
        undo: async () => {
          await Api.post( this.url( slug , "/undelete" ) , {} );
          await lists.loadLists( slug );
        },
      } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  async deleted() {
    const lists = this.lists;
    let answer;
    try {
      answer = await Api.request( "/api/lists/deleted" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    const putBack = async ( slug ) => {
      ListModal.problem( "" );
      try {
        await Undo.run( {
          label: I18n.get( "undo.list_undelete" ),
          do: async () => {
            await Api.post( this.url( slug , "/undelete" ) , {} );
            await lists.loadLists( slug );
          },
          undo: async () => {
            await Api.post( this.url( slug , "/delete" ) , {} );
            await lists.loadLists( "main" );
          },
        } );
        ListModal.close();
      } catch ( error ) {
        ListModal.problem( error.message );
      }
    };
    ListModal.open( I18n.get( "lists.deleted_title" ) , () => {
      const help = Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.deleted_help" ).replace( "{days}" , answer.days ) } );
      if ( answer.lists.length === 0 ) return { body: [ help , Dom.el( "p" , { class: "text-body-secondary mb-0" , text: I18n.get( "lists.deleted_none" ) } ) ] };
      const rows = answer.lists.map( ( list ) => Dom.el( "li" , {
        class: "list-group-item d-flex flex-wrap align-items-center gap-2",
        children: [
          Dom.el( "div" , { class: "me-auto" , children: [
            Dom.el( "div" , { class: "fw-semibold" , text: list.name } ),
            Dom.el( "div" , { class: "small text-body-secondary" , text: I18n.get( "lists.deleted_when" )
              .replace( "{when}" , () => new Date( list.deleted_at ).toLocaleString() ).replace( "{by}" , () => list.deleted_by || "?" )
              + " · " + I18n.get( "lists.count" ).replace( "{count}" , list.count ) } ),
          ] } ),
          Dom.el( "button" , { class: "btn btn-sm btn-outline-primary" , attrs: { type: "button" } , text: I18n.get( "lists.deleted_restore" ) , on: { click: () => putBack( list.slug ) } } ),
        ],
      } ) );
      return { body: [ help , Dom.el( "ul" , { class: "list-group" , children: rows } ) ] };
    } );
  },

  // ---- sharing tag and cell edits ---------------------------------------------------------

  syncMode() {
    return ( this.lists.view.doc.options && this.lists.view.doc.options.sync ) || "two-way";
  },

  setSync( mode ) {
    const old = this.syncMode();
    if ( mode === old ) return;
    this.lists.change( "undo.list_sync" , [ { op: "options" , sync: mode } ] , [ { op: "options" , sync: old } ] );
  },

  // What a write did to the other lists (the answer's `mirrored`), said once.
  report( mirrored ) {
    if ( !mirrored || mirrored.length === 0 ) return;
    const names = ( entries ) => entries.map( ( entry ) => entry.name ).join( ", " );
    const reached = mirrored.filter( ( entry ) => entry.papers );
    const skipped = mirrored.filter( ( entry ) => entry.skipped === "locked" );
    const filled = mirrored.filter( ( entry ) => entry.filled );
    const parts = [];
    if ( filled.length ) parts.push( I18n.get( "lists.filled" ).replace( "{names}" , () => filled.map( ( entry ) => entry.from.join( ", " ) ).join( ", " ) ) );
    if ( reached.length ) parts.push( I18n.get( "lists.mirrored" ).replace( "{names}" , () => names( reached ) ) );
    if ( skipped.length ) parts.push( I18n.get( "lists.mirrored_skipped" ).replace( "{names}" , () => names( skipped ) ) );
    if ( parts.length ) this.lists.state( "" , parts.join( " " ) );
  },

  // ---- Tiers: a list with sections ------------------------------------------------------------

  // Every tier's name, colour and description, its order, where added papers
  // land, adding and deleting tiers, and switching tiers on or off. Each edit
  // is an op, undoable on its own.
  tiers() {
    const lists = this.lists;
    const run = async ( label , ops , back , whole ) => {
      ListModal.problem( "" );
      const done = whole ? await lists.changeWhole( label , ops , { toast: false } ) : await lists.change( label , ops , back );
      if ( !done ) ListModal.problem( I18n.get( "lists.columns_failed" ) );
      ListModal.redraw();
    };
    const doc = () => lists.view.doc;
    ListModal.open( I18n.get( "lists.tiers_title" ) , () => {
      const sections = doc().sections || [];
      if ( sections.length === 0 ) {
        const on = Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.tiers_on" ) ,
          on: { click: () => run( "undo.list_tiers" , [ { op: "sections" , on: true } ] , null , true ) } } );
        on.disabled = lists.view.locked;
        return { body: [ Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.tiers_help_off" ) } ) ] , foot: [ on ] };
      }
      const target = ( doc().options && doc().options.section_target ) || "unranked";
      const rows = sections.map( ( section , index ) => {
        const fixed = section.id === "unranked";
        const color = Dom.el( "input" , { class: "form-control form-control-color form-control-sm tier-swatch-input" , attrs: { type: "color" , "aria-label": I18n.get( "lists.tier_colour" ).replace( "{tier}" , () => section.label ) } } );
        color.value = /^#[0-9a-f]{6}$/i.test( section.color ) ? section.color : "#8b94a3";
        color.addEventListener( "change" , () => run( "undo.list_tiers" , [ { op: "section_color" , section: section.id , color: color.value.toLowerCase() } ] , [ { op: "section_color" , section: section.id , color: section.color } ] ) );
        const name = Dom.el( "input" , { class: "form-control form-control-sm" , attrs: { type: "text" , maxlength: "60" , "aria-label": I18n.get( "lists.tier_name" ) } } );
        name.value = section.label;
        name.addEventListener( "change" , () => {
          const label = name.value.trim();
          if ( !label || label === section.label ) {
            name.value = section.label;
            return;
          }
          run( "undo.list_tiers" , [ { op: "section_rename" , section: section.id , label: label } ] , [ { op: "section_rename" , section: section.id , label: section.label } ] );
        } );
        const desc = Dom.el( "input" , { class: "form-control form-control-sm mt-1" , attrs: { type: "text" , maxlength: "400" , placeholder: I18n.get( "lists.tier_desc" ) , "aria-label": I18n.get( "lists.tier_desc" ) } } );
        desc.value = section.desc || "";
        desc.addEventListener( "change" , () => {
          if ( desc.value === ( section.desc || "" ) ) return;
          run( "undo.list_tiers" , [ { op: "section_desc" , section: section.id , desc: desc.value } ] , [ { op: "section_desc" , section: section.id , desc: section.desc || "" } ] );
        } );
        const radio = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "radio" , name: "list-tier-target" , id: "list-tier-target-" + section.id } } );
        radio.checked = target === section.id;
        radio.addEventListener( "change" , () => run( "undo.list_target" , [ { op: "section_target" , section: section.id } ] , [ { op: "section_target" , section: target } ] ) );
        const button = ( icon , key , click , disabled ) => {
          const element = Dom.el( "button" , {
            class: "btn btn-sm btn-outline-secondary" , attrs: { type: "button" , "aria-label": I18n.get( key ).replace( "{tier}" , () => section.label ) , title: I18n.get( key ).replace( "{tier}" , () => section.label ) },
            children: [ Dom.el( "i" , { class: "bi " + icon , attrs: { "aria-hidden": "true" } } ) ] , on: { click: click },
          } );
          element.disabled = Boolean( disabled );
          return element;
        };
        const up = button( "bi-arrow-up" , "lists.tier_up" , () => run( "undo.list_tiers" , [ { op: "section_move" , section: section.id , to: "up" } ] , [ { op: "section_move" , section: section.id , to: index + 1 } ] ) , fixed || index === 0 );
        const down = button( "bi-arrow-down" , "lists.tier_down" , () => run( "undo.list_tiers" , [ { op: "section_move" , section: section.id , to: "down" } ] , [ { op: "section_move" , section: section.id , to: index + 1 } ] ) , fixed || index >= sections.length - 2 );
        const remove = button( "bi-trash" , "lists.tier_delete" , async () => {
          const count = lists.sectionCounts[ section.id ] || 0;
          if ( count && !( await Dom.confirm( I18n.get( "lists.tier_delete_confirm" ).replace( "{tier}" , () => section.label ).replace( "{count}" , count ) ) ) ) return;
          run( "undo.list_tiers" , [ { op: "section_delete" , section: section.id } ] , null , true );
        } , fixed );
        remove.classList.replace( "btn-outline-secondary" , "btn-outline-danger" );
        return Dom.el( "li" , { class: "list-group-item" , children: [
          Dom.el( "div" , { class: "d-flex align-items-center gap-2" , children: [ color , name , up , down , remove ] } ),
          desc,
          Dom.el( "div" , { class: "form-check mt-1 mb-0" , children: [ radio , Dom.el( "label" , { class: "form-check-label small" , text: I18n.get( "lists.tier_is_target" ) , attrs: { for: radio.id } } ) ] } ),
        ] } );
      } );
      const fresh = Dom.el( "input" , { class: "form-control" , attrs: { type: "text" , maxlength: "60" , placeholder: I18n.get( "lists.tier_new" ) , "aria-label": I18n.get( "lists.tier_new" ) } } );
      const add = Dom.el( "button" , { class: "btn btn-outline-primary" , attrs: { type: "button" } , text: I18n.get( "lists.tier_add" ) , on: { click: () => {
        const label = fresh.value.trim();
        if ( !label ) return undefined;
        return run( "undo.list_tiers" , [ { op: "section_add" , label: label , color: TagColors.next( sections ) } ] , null , true );
      } } } );
      fresh.addEventListener( "keydown" , ( event ) => {
        if ( event.key === "Enter" ) {
          event.preventDefault();
          add.click();
        }
      } );
      const off = Dom.el( "button" , { class: "btn btn-outline-danger" , attrs: { type: "button" } , text: I18n.get( "lists.tiers_off" ) , on: { click: async () => {
        if ( await Dom.confirm( I18n.get( "lists.tiers_off_confirm" ) ) ) run( "undo.list_tiers" , [ { op: "sections" , on: false } ] , null , true );
      } } } );
      return {
        body: [
          Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.tiers_help" ) } ),
          Dom.el( "ul" , { class: "list-group mb-3" , children: rows } ),
          Dom.el( "div" , { class: "input-group" , children: [ fresh , add ] } ),
        ],
        foot: [ off ],
      };
    } );
  },

  // ---- Copy to list… --------------------------------------------------------------------------

  others() {
    return this.lists.lists.filter( ( list ) => list.slug !== this.lists.slug );
  },

  copyTo() {
    const lists = this.lists;
    const keys = ListTools.selectedKeys();
    if ( keys.length === 0 ) return;
    const from = lists.slug;
    const state = { targets: new Set() , fresh: false , freshName: "" , where: "bottom" , at: "" , mode: "copy" };
    const go = async () => {
      ListModal.problem( "" );
      const targets = Array.from( state.targets );
      const name = state.freshName.trim();
      if ( targets.length === 0 && !( state.fresh && name ) ) {
        ListModal.problem( I18n.get( "lists.copy_pick_target" ) );
        return;
      }
      const at = state.where === "at" ? Math.max( 1 , parseInt( state.at , 10 ) || 1 ) : state.where;
      const move = state.mode === "move";
      // Undo: each list back to the version it had just before (or the new
      // list into the trash). Redo: the same again, the new list taken back out.
      let made = null;
      let befores = [];
      let results = [];
      const run = async () => {
        befores = [];
        results = [];
        const all = targets.slice();
        if ( state.fresh && name ) {
          if ( made ) {
            await Api.post( this.url( made , "/undelete" ) , {} );
          } else {
            made = ( await Api.post( "/api/lists" , { name: name } ) ).list.slug;
            all.push( made );
          }
        }
        for ( const slug of all ) {
          const rev = ( await Api.request( this.url( slug ) ) ).list.rev;
          const answer = await Api.post( this.url( slug , "/ops" ) , { ops: [ { op: "import_list" , from: from , keys: keys , at: at , existing: move ? "move" : "skip" } ] } );
          if ( answer.changed ) befores.push( [ slug , rev ] );
          const listing = lists.lists.find( ( list ) => list.slug === slug );
          results.push( { slug: slug , name: listing ? listing.name : name , result: answer.results[ 0 ] } );
        }
        if ( move ) {
          const rev = lists.view.rev;
          const answer = await lists.send( from , [ { op: "remove" , rows: keys } ] );
          if ( answer.changed ) befores.push( [ from , rev ] );
          ListTools.clearSelection();
        }
        await lists.loadLists( lists.slug );
      };
      const back = async () => {
        for ( const [ slug , rev ] of befores.slice().reverse() ) {
          if ( slug === made ) continue;
          await Api.post( this.url( slug , "/restore" ) , { rev: rev } );
        }
        if ( made ) await Api.post( this.url( made , "/delete" ) , {} );
        await lists.loadLists( lists.slug === made ? from : lists.slug );
      };
      try {
        await Undo.run( { label: I18n.get( move ? "undo.list_move" : "undo.list_copy" ) , do: run , undo: back } );
      } catch ( error ) {
        ListModal.problem( error.message );
        return;
      }
      ListModal.close();
      const first = results[ 0 ];
      if ( !first ) return;
      const r = first.result;
      const parts = [];
      if ( r.imported.length ) parts.push( I18n.get( "lists.copy_done_copied" ).replace( "{count}" , r.imported.length ) );
      if ( r.moved.length ) parts.push( I18n.get( "lists.copy_done_moved" ).replace( "{count}" , r.moved.length ) );
      if ( r.skipped.length ) parts.push( I18n.get( "lists.copy_done_skipped" ).replace( "{count}" , r.skipped.length ) );
      const text = I18n.get( "lists.copy_done" ).replace( "{list}" , () => first.name ).replace( "{at}" , r.at || "–" )
        .replace( "{what}" , () => parts.join( ", " ) );
      Dom.toast( text , "ok" , { text: I18n.get( "lists.copy_open" ).replace( "{list}" , () => first.name ) , run: () => lists.loadLists( first.slug ) } );
    };
    ListModal.open( I18n.get( "lists.copy_title" ).replace( "{count}" , keys.length ) , () => {
      const check = ( id , label , on , change ) => {
        const input = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: id } } );
        input.checked = on;
        input.addEventListener( "change" , () => change( input.checked ) );
        return Dom.el( "div" , { class: "form-check" , children: [ input , Dom.el( "label" , { class: "form-check-label" , text: label , attrs: { for: id } } ) ] } );
      };
      const radio = ( group , value , label , current , change ) => {
        const id = "list-" + group + "-" + value;
        const input = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "radio" , name: "list-" + group , id: id } } );
        input.checked = current === value;
        input.addEventListener( "change" , () => {
          change( value );
          ListModal.redraw();
        } );
        return Dom.el( "div" , { class: "form-check form-check-inline" , children: [ input , Dom.el( "label" , { class: "form-check-label" , text: label , attrs: { for: id } } ) ] } );
      };
      const targets = this.others().map( ( list ) => check( "list-copy-" + list.slug , list.name , state.targets.has( list.slug ) , ( on ) => {
        if ( on ) state.targets.add( list.slug );
        else state.targets.delete( list.slug );
      } ) );
      targets.push( check( "list-copy-fresh" , I18n.get( "lists.copy_new_list" ) , state.fresh , ( on ) => {
        state.fresh = on;
        ListModal.redraw();
      } ) );
      if ( state.fresh ) {
        const name = Dom.el( "input" , { class: "form-control form-control-sm mt-1" , attrs: { type: "text" , maxlength: "80" , "aria-label": I18n.get( "lists.copy_new_name" ) , placeholder: I18n.get( "lists.copy_new_name" ) } } );
        name.value = state.freshName;
        name.addEventListener( "input" , () => { state.freshName = name.value; } );
        targets.push( name );
      }
      const where = [
        radio( "copy-where" , "top" , I18n.get( "lists.where_top_short" ) , state.where , ( value ) => { state.where = value; } ),
        radio( "copy-where" , "bottom" , I18n.get( "lists.where_bottom_short" ) , state.where , ( value ) => { state.where = value; } ),
        radio( "copy-where" , "at" , I18n.get( "lists.where_at" ) , state.where , ( value ) => { state.where = value; } ),
      ];
      if ( state.where === "at" ) {
        const at = Dom.el( "input" , { class: "form-control form-control-sm board-row-num d-inline-block" , attrs: { type: "text" , inputmode: "numeric" , "aria-label": I18n.get( "lists.where_at" ) } } );
        at.value = state.at;
        at.addEventListener( "input" , () => { state.at = at.value.trim(); } );
        where.push( at );
      }
      const legend = ( key ) => Dom.el( "legend" , { class: "form-label small fw-semibold mb-1" , text: I18n.get( key ) } );
      return {
        body: [
          Dom.el( "fieldset" , { class: "mb-3" , children: [ legend( "lists.copy_targets" ) ].concat( targets ) } ),
          Dom.el( "fieldset" , { class: "mb-3" , children: [ legend( "lists.copy_where" ) ].concat( where ) } ),
          Dom.el( "fieldset" , { class: "mb-2" , children: [ legend( "lists.copy_mode" ) ,
            radio( "copy-mode" , "copy" , I18n.get( "lists.copy_copy" ) , state.mode , ( value ) => { state.mode = value; } ),
            radio( "copy-mode" , "move" , I18n.get( "lists.copy_move" ) , state.mode , ( value ) => { state.mode = value; } ) ] } ),
          Dom.el( "p" , { class: "form-text mb-0" , text: I18n.get( "lists.copy_help" ) } ),
        ],
        foot: [ Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( state.mode === "move" ? "lists.move_go" : "lists.copy_go" ) , on: { click: go } } ) ],
      };
    } );
  },

  // ---- Import from lists… -----------------------------------------------------------------------

  // Folded the way the server's filter reads text: case and accents aside.
  fold( text ) {
    return String( text || "" ).normalize( "NFD" ).replace( /[̀-ͯ]/g , "" ).toLowerCase();
  },

  // "1-40, 55" -> Set of positions, or null for nothing typed. Throws on junk.
  range( spec ) {
    const text = String( spec || "" ).trim();
    if ( !text ) return null;
    const out = new Set();
    text.split( /[,\s]+/ ).filter( Boolean ).forEach( ( part ) => {
      const match = part.match( /^#?(\d+)(?:[-–](\d+))?$/ );
      if ( !match ) throw new Error( part );
      let a = parseInt( match[ 1 ] , 10 );
      let b = match[ 2 ] ? parseInt( match[ 2 ] , 10 ) : a;
      if ( b < a ) [ a , b ] = [ b , a ];
      for ( let n = a ; n <= b && n - a < 100000 ; n++ ) out.add( n );
    } );
    return out;
  },

  // The dialog's filters over [ { pos , row } ], as ops.pick_rows reads them.
  pick( rows , filter ) {
    const want = filter.tags.split( "," ).map( ( tag ) => tag.trim().toLowerCase() ).filter( Boolean );
    const span = this.range( filter.range );
    const y0 = parseInt( filter.yearFrom , 10 );
    const y1 = parseInt( filter.yearTo , 10 );
    const bounded = Number.isFinite( y0 ) || Number.isFinite( y1 );
    const terms = this.fold( filter.q ).split( /\s+/ ).filter( Boolean );
    return rows.filter( ( { pos , row } ) => {
      if ( span && !span.has( pos ) ) return false;
      const tags = ( row.tags || [] ).map( ( tag ) => tag.toLowerCase() );
      if ( want.length ) {
        const hits = want.filter( ( tag ) => tags.includes( tag ) ).length;
        if ( filter.match === "any" && hits === 0 ) return false;
        if ( filter.match === "all" && hits < want.length ) return false;
        if ( filter.match === "none" && hits > 0 ) return false;
      }
      const year = parseInt( row.year , 10 );
      if ( !Number.isFinite( year ) ) {
        if ( bounded ) return false;
      } else if ( ( Number.isFinite( y0 ) && year < y0 ) || ( Number.isFinite( y1 ) && year > y1 ) ) {
        return false;
      }
      if ( terms.length ) {
        const hay = this.fold( [ row.title , row.key , row.doi , ( row.tags || [] ).join( " " ) , Object.values( row.fields || {} ).join( " " ) ].join( " " ) );
        if ( !terms.every( ( term ) => hay.includes( term ) ) ) return false;
      }
      return true;
    } );
  },

  async importFrom() {
    const lists = this.lists;
    const slug = lists.slug;
    const others = this.others();
    const state = { source: others.length ? others[ 0 ].slug : "~remaining" , rows: [] , picked: new Set() , anchor: -1 ,
      filter: { tags: "" , match: "any" , yearFrom: "" , yearTo: "" , q: "" , range: "" } , land: "bottom" , at: "" , error: "" };
    const cache = {};
    const load = async () => {
      state.picked = new Set();
      if ( !cache[ state.source ] ) {
        if ( state.source === "~remaining" ) {
          const answer = await Api.request( this.url( slug , "/remaining" ) );
          cache[ state.source ] = answer.papers.map( ( paper ) => Object.assign( {} , paper , { tags: paper.mods || [] } ) );
        } else {
          cache[ state.source ] = ( await Api.request( this.url( state.source ) ) ).list.doc.items || [];
        }
      }
      state.rows = cache[ state.source ].map( ( row , index ) => ( { pos: index + 1 , row: row } ) );
    };
    const here = () => {
      const keys = new Set();
      ( lists.view.doc.items || [] ).concat( lists.view.doc.staging || [] ).forEach( ( row ) => {
        keys.add( row.key.toLowerCase() );
        if ( row.doi ) keys.add( row.doi.toLowerCase() );
      } );
      return keys;
    };
    const isHere = ( have , row ) => have.has( String( row.key ).toLowerCase() ) || Boolean( row.doi && have.has( row.doi.toLowerCase() ) );
    const shown = () => {
      try {
        state.error = "";
        return this.pick( state.rows , state.filter );
      } catch ( error ) {
        state.error = error.message;
        return [];
      }
    };
    const go = async () => {
      ListModal.problem( "" );
      const have = here();
      const passing = shown().filter( ( entry ) => !isHere( have , entry.row ) );
      const keys = ( state.picked.size ? passing.filter( ( entry ) => state.picked.has( entry.pos ) ) : passing ).map( ( entry ) => entry.row.key );
      if ( keys.length === 0 ) return;
      const op = state.source === "~remaining" ? { op: "import_remaining" , keys: keys } : { op: "import_list" , from: state.source , keys: keys };
      if ( state.land === "shelf" ) op.shelf = true;
      else op.at = state.land === "at" ? Math.max( 1 , parseInt( state.at , 10 ) || 1 ) : state.land;
      const answer = await lists.changeWhole( "undo.list_import" , [ op ] );
      if ( !answer ) return;
      ListModal.close();
      Dom.toast( I18n.get( "lists.import_done" ).replace( "{imported}" , answer.results[ 0 ].imported.length ) , "ok" );
    };
    try {
      await load();
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    let typing = null;
    const refilter = () => {
      clearTimeout( typing );
      typing = setTimeout( () => {
        state.picked = new Set();
        ListModal.redraw();
      } , 250 );
    };
    // Built once, so typing in them never loses the caret to a redraw.
    const field = ( key , label , attrs ) => {
      const id = "list-import-" + key;
      const input = Dom.el( "input" , { class: "form-control form-control-sm" , attrs: Object.assign( { type: "text" , id: id } , attrs || {} ) } );
      input.value = state.filter[ key ];
      input.addEventListener( "input" , () => {
        state.filter[ key ] = input.value;
        refilter();
      } );
      return Dom.el( "div" , { class: "col-6 col-md" , children: [ Dom.el( "label" , { class: "form-label small mb-0" , text: I18n.get( label ) , attrs: { for: id } } ) , input ] } );
    };
    const source = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { id: "list-import-source" } } );
    others.forEach( ( list ) => source.appendChild( Dom.el( "option" , { text: list.name , attrs: { value: list.slug } } ) ) );
    source.appendChild( Dom.el( "option" , { text: I18n.get( "lists.import_remaining" ) , attrs: { value: "~remaining" } } ) );
    source.value = state.source;
    source.addEventListener( "change" , async () => {
      state.source = source.value;
      try {
        await load();
      } catch ( error ) {
        ListModal.problem( error.message );
      }
      ListModal.redraw();
    } );
    const match = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { id: "list-import-match" , "aria-label": I18n.get( "lists.filter_match_label" ) } } );
    [ "any" , "all" , "none" ].forEach( ( value ) => match.appendChild( Dom.el( "option" , { text: I18n.get( "lists.match_" + value ) , attrs: { value: value } } ) ) );
    match.addEventListener( "change" , () => {
      state.filter.match = match.value;
      refilter();
    } );
    const filters = Dom.el( "div" , { class: "row g-2 mb-2" , children: [
      Dom.el( "div" , { class: "col-12" , children: [ Dom.el( "label" , { class: "form-label small mb-0" , text: I18n.get( "lists.import_source" ) , attrs: { for: "list-import-source" } } ) , source ] } ),
      field( "tags" , "lists.import_tags" , { placeholder: I18n.get( "lists.import_tags_placeholder" ) , list: "list-tag-options" } ),
      Dom.el( "div" , { class: "col-6 col-md-auto d-flex align-items-end" , children: [ match ] } ),
      field( "yearFrom" , "lists.import_year_from" , { inputmode: "numeric" } ),
      field( "yearTo" , "lists.import_year_to" , { inputmode: "numeric" } ),
      field( "q" , "lists.import_text" ),
      field( "range" , "lists.import_range" , { placeholder: I18n.get( "lists.import_range_placeholder" ) } ),
    ] } );
    const SHOW = 400;
    ListModal.open( I18n.get( "lists.import_title" ) , () => {
      const have = here();
      const passing = shown();
      const fresh = passing.filter( ( entry ) => !isHere( have , entry.row ) );
      const visible = passing.slice( 0 , SHOW );
      const index = new Map( visible.map( ( entry , i ) => [ entry.pos , i ] ) );
      const onPick = ( entry , event ) => {
        if ( isHere( have , entry.row ) ) return;
        const at = index.get( entry.pos );
        if ( event.metaKey || event.ctrlKey ) {
          if ( state.picked.has( entry.pos ) ) state.picked.delete( entry.pos );
          else state.picked.add( entry.pos );
          state.anchor = at;
        } else if ( event.shiftKey && state.anchor >= 0 ) {
          visible.slice( Math.min( state.anchor , at ) , Math.max( state.anchor , at ) + 1 )
            .filter( ( each ) => !isHere( have , each.row ) ).forEach( ( each ) => state.picked.add( each.pos ) );
        } else {
          state.picked = new Set( [ entry.pos ] );
          state.anchor = at;
        }
        ListModal.redraw();
      };
      const rows = visible.map( ( entry ) => {
        const already = isHere( have , entry.row );
        const tr = Dom.el( "tr" , {
          class: ( already ? "text-body-secondary" : "" ) + ( state.picked.has( entry.pos ) ? " table-primary" : "" ),
          children: [
            Dom.el( "td" , { class: "text-end" , text: String( entry.pos ) } ),
            Dom.el( "td" , { children: [ Dom.el( "span" , { text: entry.row.title || entry.row.key } ) ].concat(
              already ? [ Dom.el( "span" , { class: "badge text-bg-secondary ms-2" , text: I18n.get( "lists.import_already" ) } ) ] : [] ) } ),
            Dom.el( "td" , { text: entry.row.year ? String( entry.row.year ) : "" } ),
            Dom.el( "td" , { class: "small" , text: ( entry.row.tags || [] ).join( ", " ) } ),
          ],
        } );
        tr.addEventListener( "mousedown" , ( event ) => {
          event.preventDefault();
          onPick( entry , event );
        } );
        return tr;
      } );
      const head = Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: [ "col_position" , "col_title" , "col_year" , "col_tags" ].map( ( key ) => Dom.el( "th" , { attrs: { scope: "col" } , text: I18n.get( "lists." + key ) } ) ) } ) ] } );
      const table = Dom.el( "div" , { class: "import-preview border rounded" , children: [ Dom.el( "div" , { class: "table-responsive" , children: [
        Dom.el( "table" , { class: "table table-sm table-hover mb-0 user-select-none" , children: [ head , Dom.el( "tbody" , { children: rows } ) ] } ),
      ] } ) ] } );
      const picked = fresh.filter( ( entry ) => state.picked.has( entry.pos ) ).length;
      const count = picked || fresh.length;
      const land = Dom.el( "select" , { class: "form-select form-select-sm w-auto" , attrs: { id: "list-import-land" } } );
      [ [ "bottom" , "lists.where_bottom_short" ] , [ "top" , "lists.where_top_short" ] , [ "at" , "lists.where_at" ] , [ "shelf" , "lists.import_to_shelf" ] ]
        .forEach( ( [ value , key ] ) => land.appendChild( Dom.el( "option" , { text: I18n.get( key ) , attrs: { value: value } } ) ) );
      land.value = state.land;
      land.addEventListener( "change" , () => {
        state.land = land.value;
        ListModal.redraw();
      } );
      const foot = [ Dom.el( "label" , { class: "small text-body-secondary" , text: I18n.get( "lists.import_to" ) , attrs: { for: "list-import-land" } } ) , land ];
      if ( state.land === "at" ) {
        const at = Dom.el( "input" , { class: "form-control form-control-sm board-row-num" , attrs: { type: "text" , inputmode: "numeric" , "aria-label": I18n.get( "lists.where_at" ) } } );
        at.value = state.at;
        at.addEventListener( "input" , () => { state.at = at.value.trim(); } );
        foot.push( at );
      }
      const button = Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.import_go" ).replace( "{count}" , count ) , on: { click: go } } );
      button.disabled = count === 0;
      foot.push( button );
      const body = [
        filters,
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.import_help" ) } ),
        Dom.el( "p" , { class: "small fw-semibold mb-1" , text: I18n.get( "lists.import_counts" ).replace( "{shown}" , passing.length ).replace( "{fresh}" , fresh.length ).replace( "{picked}" , picked ) } ),
        table,
      ];
      if ( passing.length > SHOW ) body.push( Dom.el( "p" , { class: "small text-body-secondary mt-1" , text: I18n.get( "lists.import_more" ).replace( "{count}" , passing.length - SHOW ) } ) );
      if ( state.error ) body.push( Dom.el( "p" , { class: "small text-danger mt-1" , text: I18n.get( "lists.import_range" ) + ": " + state.error } ) );
      return { body: body , foot: foot };
    } );
  },
};
