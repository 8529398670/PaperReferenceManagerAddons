// The Paper screen: one paper, #paper/<key>, linked from every title.
//
// Everything the library knows of it (Zotero's record), what the content
// stages have made of it so far (its sections, code and dataset links,
// modality tags, its OpenAlex network) and how each stage stands, with Retry
// on a failed one. Opening it moves its unfinished stages to the front of the
// queue; the "paper" events on the library's stream then fill it in place.
//
// Opened from a list, Prev / Next step through that list (PaperView.context,
// set by the title link that was clicked).
const PaperView = {
  key: "",
  context: null,
  ticket: 0,
  timer: null,
  stages: [ "openalex" , "methods" , "code" , "datasets" , "modalities" ],

  init() {
    Dom.show( Dom.get( "paper-panel" ) , true );
    window.addEventListener( "hashchange" , () => this.route() );
    const reload = Content.throttle( () => this.load( false ) , 3000 );
    Content.on( "paper" , ( data ) => {
      if ( data.key !== this.key || Nav.current() !== "paper" ) return;
      reload();
    } );
    Dom.onPress( Dom.get( "paper-prev" ) , () => this.step( -1 ) );
    Dom.onPress( Dom.get( "paper-next" ) , () => this.step( 1 ) );
    this.route();
  },

  keyOfHash() {
    const hash = window.location.hash.replace( /^#/ , "" );
    if ( !hash.startsWith( "paper/" ) ) return "";
    try {
      return decodeURIComponent( hash.slice( "paper/".length ) );
    } catch ( error ) {
      return "";
    }
  },

  route() {
    const key = this.keyOfHash();
    if ( !key ) return;
    if ( key !== this.key ) {
      this.key = key;
      this.load( true );
    }
  },

  async load( fresh ) {
    const ticket = ++this.ticket;
    const key = this.key;
    if ( fresh ) {
      Dom.text( Dom.get( "paper-title" ) , I18n.get( "paper.loading" ) );
      Dom.show( Dom.get( "paper-body" ) , false );
      Dom.show( Dom.get( "paper-missing" ) , false );
    }
    let paper;
    let content;
    try {
      [ paper , content ] = await Promise.all( [
        Api.request( "/api/paper?key=" + encodeURIComponent( key ) ),
        Api.request( "/api/paper/content?key=" + encodeURIComponent( key ) ),
      ] );
    } catch ( error ) {
      if ( ticket !== this.ticket ) return;
      Dom.text( Dom.get( "paper-title" ) , I18n.get( "paper.heading" ) );
      Dom.text( Dom.get( "paper-missing" ) , error.status === 404 ? I18n.get( "paper.not_found" ) : error.message );
      Dom.show( Dom.get( "paper-missing" ) , true );
      return;
    }
    if ( ticket !== this.ticket ) return;
    await PaperLinks.init();
    this.draw( paper.paper , content );
    Dom.show( Dom.get( "paper-body" ) , true );
    if ( fresh ) Nav.announce( "paper" );
  },

  draw( paper , answer ) {
    const content = answer.content;
    Dom.text( Dom.get( "paper-title" ) , paper.title || paper.key );
    Dom.text( Dom.get( "paper-meta" ) , [ ( paper.authors || [] ).join( ", " ) , paper.year || "" , paper.journal || "" ].filter( Boolean ).join( " · " ) );
    const links = PaperLinks.strip( paper );
    if ( content.openalex_url ) {
      links.appendChild( PaperLinks.link( content.openalex_url , "paper.openalex_link" , "paper.openalex_link_title" ) );
    }
    Dom.swap( Dom.get( "paper-links" ) , links , Content.strip( paper.key , this.badgeOf( content ) ) );
    this.drawTags( paper , answer.lists );
    this.drawNav();
    this.drawStages( content.stages );
    this.drawAbstract( paper , content );
    this.drawNetwork( paper , content );
    this.drawLinks( content );
    this.drawSections( content.sections || [] );
  },

  // The badge summary, from the full content (the same shape the rows get).
  badgeOf( content ) {
    const states = {};
    const errors = {};
    this.stages.forEach( ( stage ) => {
      const task = content.stages[ stage ] || {};
      states[ stage ] = task.state || "none";
      if ( task.error ) errors[ stage ] = task.error;
    } );
    const methods = ( content.stages.methods || {} ).summary || {};
    return {
      states: states , errors: errors , mods: content.modalities ,
      code: states.code === "done" ? content.code.length : 0,
      data: states.datasets === "done" ? content.data.length + content.names.length : 0,
      methods: Boolean( methods.methods_chars ),
      refs: ( content.network || {} ).refs , citers: ( content.network || {} ).citers,
    };
  },

  drawTags( paper , lists ) {
    const holder = Dom.get( "paper-tags" );
    Dom.clear( holder );
    ( paper.tags || [] ).forEach( ( tag ) => holder.appendChild( TagColors.paint( Dom.el( "span" , { class: "badge tag-chip" , text: tag } ) , tag ) ) );
    ( paper.collections || [] ).forEach( ( name ) => {
      holder.appendChild( Dom.el( "span" , { class: "badge text-bg-light border" , children: [
        Dom.el( "i" , { class: "bi bi-folder2" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: " " + name } ),
      ] } ) );
    } );
    const on = Dom.get( "paper-lists" );
    Dom.clear( on );
    Dom.show( on , lists.length > 0 );
    if ( lists.length ) {
      on.appendChild( Dom.el( "span" , { class: "text-body-secondary" , text: I18n.get( "paper.on_lists" ) + " " } ) );
      lists.forEach( ( list , index ) => {
        if ( index ) on.appendChild( document.createTextNode( ", " ) );
        on.appendChild( Dom.el( "a" , {
          text: I18n.get( "paper.on_list" ).replace( "{name}" , () => list.name ).replace( "{position}" , list.position ),
          attrs: { href: "#lists/" + encodeURIComponent( list.slug ) },
        } ) );
      } );
    }
  },

  drawNav() {
    const context = this.context;
    const index = context ? context.keys.indexOf( this.key ) : -1;
    Dom.show( Dom.get( "paper-nav" ) , index >= 0 );
    if ( index < 0 ) return;
    Dom.get( "paper-prev" ).disabled = index === 0;
    Dom.get( "paper-next" ).disabled = index === context.keys.length - 1;
    const back = Dom.get( "paper-back" );
    back.setAttribute( "href" , "#lists/" + encodeURIComponent( context.slug ) );
    Dom.text( back , I18n.get( "paper.back_to" ).replace( "{name}" , () => context.name ).replace( "{n}" , index + 1 ).replace( "{total}" , context.keys.length ) );
  },

  step( delta ) {
    const context = this.context;
    if ( !context ) return;
    const next = context.keys[ context.keys.indexOf( this.key ) + delta ];
    if ( next ) window.location.hash = "#paper/" + encodeURIComponent( next );
  },

  drawStages( stages ) {
    const body = Dom.get( "paper-stages" );
    Dom.clear( body );
    this.stages.forEach( ( stage ) => {
      const task = stages[ stage ] || { state: "none" };
      const state = Dom.el( "td" , { children: [ this.stateBadge( task.state ) ] } );
      const detail = Dom.el( "td" , { class: "small text-body-secondary" , text: this.detail( stage , task ) } );
      const action = Dom.el( "td" , { class: "text-end" } );
      if ( task.state === "failed" || task.state === "not_found" || ( stage === "openalex" && task.state === "done" && ( task.summary || {} ).cut ) ) {
        action.appendChild( Dom.el( "button" , {
          class: "btn btn-outline-secondary btn-sm",
          text: I18n.get( "content.retry" ),
          on: { click: () => this.retry( stage ) },
        } ) );
      }
      body.appendChild( Dom.el( "tr" , { children: [ Dom.el( "th" , { attrs: { scope: "row" } , text: Content.stageName( stage ) } ) , state , detail , action ] } ) );
    } );
    Content.label( body.closest( "table" ) );
  },

  stateBadge( state ) {
    const tones = {
      done: "bg-success-subtle text-success-emphasis border", pending: "text-bg-light border", running: "text-bg-light border",
      failed: "bg-danger-subtle text-danger-emphasis border", not_found: "bg-warning-subtle text-warning-emphasis border", none: "text-bg-light border",
    };
    return Content.chip( I18n.get( "content.state_" + state ) , tones[ state ] || tones.none , state === "pending" || state === "running" ? "spin" : "" , "" );
  },

  detail( stage , task ) {
    if ( task.error ) return I18n.get( "content.why" ).replace( "{error}" , () => task.error ).replace( "{attempts}" , task.attempts || 0 );
    const summary = task.summary || {};
    if ( task.state !== "done" ) return "";
    if ( stage === "openalex" ) {
      let text = I18n.get( "paper.openalex_summary" ).replace( "{refs}" , summary.refs || 0 ).replace( "{citers}" , summary.citers || 0 );
      if ( summary.cut ) text += " " + I18n.get( "paper.openalex_cut" );
      if ( summary.via_title ) text += " " + I18n.get( "paper.openalex_via_title" );
      return text;
    }
    if ( stage === "methods" ) {
      if ( !summary.has_text ) return I18n.get( "paper.no_text" );
      return summary.methods_chars ? I18n.get( "paper.methods_summary" ).replace( "{sections}" , summary.sections || 0 ) : I18n.get( "paper.no_methods" );
    }
    if ( stage === "code" || stage === "datasets" ) return I18n.get( "paper.links_summary" ).replace( "{n}" , ( summary.n || 0 ) + ( summary.names || 0 ) );
    if ( stage === "modalities" ) {
      const used = ( summary.used || [] ).join( ", " ) || I18n.get( "paper.no_modalities" );
      return summary.inferred ? I18n.get( "paper.modalities_inferred" ).replace( "{used}" , () => used ) : used;
    }
    return "";
  },

  async retry( stage ) {
    await Api.post( "/api/papers/retry" , { key: this.key , stage: stage } );
    await this.load( false );
  },

  drawAbstract( paper , content ) {
    const text = paper.abstract || content.openalex_abstract || "";
    Dom.text( Dom.get( "paper-abstract" ) , text || I18n.get( "paper.no_abstract" ) );
    Dom.get( "paper-abstract" ).classList.toggle( "text-body-secondary" , !text );
    Dom.show( Dom.get( "paper-abstract-source" ) , !paper.abstract && Boolean( content.openalex_abstract ) );
  },

  drawNetwork( paper , content ) {
    const holder = Dom.get( "paper-network" );
    Dom.clear( holder );
    const network = content.network || {};
    if ( !network.wid ) {
      holder.appendChild( Dom.el( "p" , { class: "text-body-secondary mb-0" , text: I18n.get( "paper.network_pending" ) } ) );
      return;
    }
    const line = ( textKey , n , inLib ) => Dom.el( "li" , {
      text: I18n.get( textKey ).replace( "{n}" , n || 0 ).replace( "{in_lib}" , inLib || 0 ).replace( "{missing}" , Math.max( ( n || 0 ) - ( inLib || 0 ) , 0 ) ),
    } );
    holder.appendChild( Dom.el( "ul" , { class: "list-unstyled mb-2" , children: [
      line( "paper.refs_line" , network.refs , network.refs_in_lib ),
      line( "paper.citers_line" , network.citers , network.citers_in_lib ),
      Dom.el( "li" , { class: "text-body-secondary small" , text: I18n.get( "paper.cited_by_count" ).replace( "{n}" , ( network.cited_by_count || 0 ).toLocaleString() ) } ),
    ] } ) );
    holder.appendChild( Dom.el( "a" , {
      class: "btn btn-outline-primary btn-sm",
      attrs: { href: "#missing/" + encodeURIComponent( paper.key ) },
      children: [ Dom.el( "i" , { class: "bi bi-diagram-3" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { text: " " + I18n.get( "paper.network_missing" ) } ) ],
    } ) );
  },

  drawLinks( content ) {
    const holder = Dom.get( "paper-found" );
    Dom.clear( holder );
    const group = ( headingKey , items , make ) => {
      if ( !items.length ) return;
      holder.appendChild( Dom.el( "h3" , { class: "h6 mt-2" , text: I18n.get( headingKey ) } ) );
      holder.appendChild( Dom.el( "ul" , { class: "list-unstyled mb-2 paper-found-list" , children: items.map( make ) } ) );
    };
    const link = ( entry ) => Dom.el( "li" , { children: [
      Dom.el( "a" , { text: entry.url , attrs: { href: entry.url , target: "_blank" , rel: "noopener" } } ),
      Dom.el( "span" , { class: "text-body-secondary small" , text: " · " + [ entry.host , entry.where ].filter( Boolean ).join( " · " ) } ),
    ] } );
    group( "paper.code_heading" , content.code || [] , link );
    group( "paper.data_heading" , content.data || [] , link );
    group( "paper.names_heading" , content.names || [] , ( entry ) => Dom.el( "li" , { children: [
      entry.url ? Dom.el( "a" , { text: entry.name , attrs: { href: entry.url , target: "_blank" , rel: "noopener" } } ) : Dom.el( "span" , { text: entry.name } ),
      Dom.el( "span" , { class: "text-body-secondary small" , text: entry.description ? " · " + entry.description : "" } ),
    ] } ) );
    if ( !holder.children.length ) {
      const done = content.stages.code && content.stages.code.state === "done";
      holder.appendChild( Dom.el( "p" , { class: "text-body-secondary mb-0" , text: I18n.get( done ? "paper.no_links" : "paper.links_pending" ) } ) );
    }
  },

  drawSections( sections ) {
    const toc = Dom.get( "paper-toc" );
    const accordion = Dom.get( "paper-sections" );
    Dom.clear( toc );
    Dom.clear( accordion );
    const shown = sections.filter( ( section ) => ( section.text || "" ).trim() );
    Dom.show( Dom.get( "paper-sections-empty" ) , shown.length === 0 );
    shown.forEach( ( section , index ) => {
      const id = "paper-section-" + index;
      const label = section.heading || I18n.get( "paper.section_" + section.key ) || section.key;
      const isMethods = section.key === "methods";
      const kind = I18n.get( "paper.section_" + section.key ) || section.key;
      toc.appendChild( Dom.el( "li" , { children: [ Dom.el( "a" , {
        text: label,
        attrs: { href: "#" + id },
        on: { click: ( event ) => {
          event.preventDefault();
          const panel = Dom.get( id + "-body" );
          if ( window.bootstrap ) bootstrap.Collapse.getOrCreateInstance( panel , { toggle: false } ).show();
          Dom.reveal( Dom.get( id ) , "start" );
        } },
      } ) ] } ) );
      const button = Dom.el( "button" , {
        class: "accordion-button" + ( isMethods ? "" : " collapsed" ),
        attrs: { type: "button" , "data-bs-toggle": "collapse" , "data-bs-target": "#" + id + "-body" , "aria-expanded": String( isMethods ) , "aria-controls": id + "-body" },
        children: [ Dom.el( "span" , { text: label } ) , kind.toLowerCase() === label.toLowerCase() ? null : Dom.el( "span" , { class: "badge text-bg-light border ms-2" , text: kind } ) ].filter( Boolean ),
      } );
      const body = Dom.el( "div" , { class: "accordion-body paper-section-text" } );
      ( section.text || "" ).split( /\n{2,}/ ).forEach( ( para ) => {
        if ( para.trim() ) body.appendChild( Dom.el( "p" , { text: para.trim() } ) );
      } );
      accordion.appendChild( Dom.el( "div" , { class: "accordion-item" , attrs: { id: id } , children: [
        Dom.el( "h3" , { class: "accordion-header" , children: [ button ] } ),
        Dom.el( "div" , { class: "accordion-collapse collapse" + ( isMethods ? " show" : "" ) , attrs: { id: id + "-body" } , children: [ body ] } ),
      ] } ) );
    } );
  },
};
