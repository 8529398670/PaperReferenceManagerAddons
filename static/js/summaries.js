// LLM summaries (app/extras/summaries.py): made only when asked, never on
// their own, since each one costs money.
//
//   - the Paper screen's Summaries card: each section summarised so far, and a
//     Summarize button for one section;
//   - a list's selection: Summarize asks which sections, then queues them;
//   - the Summaries screen: one section's summaries rolled up into a table,
//     the "**Subsection.**" headers the prompts ask for as columns, the
//     hashtags as chips (click one to filter), and the .xlsx of it all.
//
// Progress arrives on the library stream ("summary" {key, section, state}).
const SummariesView = {
  sections: [],
  status: {},
  rows: [],
  tag: "",
  paperKey: "",
  asking: null,

  init() {
    Dom.show( Dom.get( "summaries-panel" ) , true );
    Dom.get( "rollup-section" ).addEventListener( "change" , () => this.loadRollup() );
    Dom.typed( Dom.get( "rollup-search" ) , () => this.drawRollup() , 200 );
    Dom.onPress( Dom.get( "summaries-cancel" ) , async () => {
      await Api.post( "/api/summaries/cancel" , {} );
      this.loadStatus();
    } );
    Dom.onPress( Dom.get( "paper-summarize" ) , () => this.summarizePaper() );
    Dom.onPress( Dom.get( "list-summarize" ) , () => this.ask( ListTools.selectedKeys() , I18n.get( "summaries.what_selection" ).replace( "{n}" , ListTools.selectedKeys().length ) ) );
    Dom.onSubmit( Dom.get( "summarize-form" ) , ( event ) => {
      event.preventDefault();
      return this.queue();
    } );
    const soon = Content.throttle( () => {
      this.loadStatus();
      if ( Nav.current() === "summaries" ) this.loadRollup();
    } , 5000 );
    Content.on( "summary" , ( data ) => {
      if ( data.key && data.key === this.paperKey ) this.loadPaper();
      if ( data.state === "failed" && data.error && data.key === this.paperKey ) Dom.toast( data.error , "error" );
      soon();
    } );
    window.addEventListener( "hashchange" , () => { if ( Nav.current() === "summaries" ) this.loadRollup(); } );
    this.loadStatus().then( () => { if ( Nav.current() === "summaries" ) this.loadRollup(); } );
  },

  async loadStatus() {
    try {
      this.status = await Api.request( "/api/summaries/status" );
    } catch ( error ) {
      return;
    }
    if ( !this.sections.length ) {
      this.sections = this.status.sections;
      [ Dom.get( "rollup-section" ) , Dom.get( "paper-summary-section" ) ].forEach( ( picker ) => {
        Dom.clear( picker );
        this.sections.forEach( ( [ key , name ] ) => picker.appendChild( Dom.el( "option" , { text: name , attrs: { value: key } } ) ) );
      } );
      Dom.get( "rollup-section" ).value = "methods";
      Dom.get( "paper-summary-section" ).value = "methods";
    }
    const s = this.status;
    Dom.show( Dom.get( "summaries-no-model" ) , !s.provider );
    Dom.get( "paper-summarize" ).disabled = !s.provider;
    const parts = [ s.provider ? I18n.get( "summaries.model_line" ).replace( "{provider}" , s.provider ).replace( "{model}" , s.model ) : "" ];
    if ( s.queued || s.running ) parts.push( I18n.get( "summaries.queue_line" ).replace( "{queued}" , s.queued ).replace( "{running}" , s.running ? 1 : 0 ) );
    if ( s.failed ) parts.push( I18n.get( "summaries.failed_line" ).replace( "{n}" , s.failed ) );
    Dom.text( Dom.get( "summaries-status" ) , parts.filter( Boolean ).join( " · " ) );
    Dom.show( Dom.get( "summaries-cancel" ) , s.queued > 0 );
  },

  // -- the rollup -------------------------------------------------------------------

  async loadRollup() {
    const section = Dom.get( "rollup-section" ).value || "methods";
    Dom.get( "rollup-export" ).setAttribute( "href" , "/api/summaries/rollup.xlsx?section=" + encodeURIComponent( section ) );
    let answer;
    try {
      answer = await Api.request( "/api/summaries/rollup?section=" + encodeURIComponent( section ) );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.rollup = answer;
    this.table = new DataTable( {
      name: "rollup-" + section,
      holder: Dom.get( "rollup-table" ),
      menu: Dom.get( "rollup-columns" ),
      columns: this.rollupColumns( answer ),
      sort: [ { col: "title" , desc: false } ],
    } );
    this.table.drawMenu();
    this.drawTags();
    this.drawRollup();
  },

  rollupColumns( answer ) {
    const text = ( value ) => Dom.el( "div" , { class: "small rollup-cell" , text: value || "" } );
    const columns = [
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , lock: true , width: 18 , cell: ( row ) => Dom.el( "a" , {
        class: "paper-title" , text: row.title , attrs: { href: "#paper/" + encodeURIComponent( row.key ) } } ) },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 5 , cell: ( row ) => row.year || "" },
      { id: "hashtags" , label: "summaries.col_hashtags" , width: 12 , cell: ( row ) => text( row.hashtags ) },
    ];
    answer.columns.forEach( ( name , index ) => columns.push( { id: "part-" + index , text: name , width: 22 , value: ( row ) => row.parts[ name ] || "" , cell: ( row ) => text( row.parts[ name ] ) } ) );
    answer.extra.forEach( ( name , index ) => columns.push( { id: "extra-" + index , text: name , width: 22 , value: ( row ) => row.extra[ name ] || "" , cell: ( row ) => text( row.extra[ name ] ) } ) );
    columns.push( { id: "model" , label: "summaries.col_model" , width: 8 , hide: true , cellClass: "small text-body-secondary" , cell: ( row ) => row.model || "" } );
    return columns;
  },

  drawTags() {
    const holder = Dom.get( "rollup-tags" );
    Dom.clear( holder );
    ( this.rollup.hashtags || [] ).slice( 0 , 40 ).forEach( ( [ tag , n ] ) => {
      const on = this.tag === tag;
      holder.appendChild( Dom.el( "button" , {
        class: "btn btn-sm " + ( on ? "btn-primary" : "btn-outline-secondary" ),
        text: tag + " " + n,
        attrs: { type: "button" , "aria-pressed": String( on ) },
        on: { click: () => { this.tag = on ? "" : tag; this.drawTags(); this.drawRollup(); } },
      } ) );
    } );
  },

  drawRollup() {
    if ( !this.rollup ) return;
    const words = Dom.get( "rollup-search" ).value.trim().toLowerCase().split( /\s+/ ).filter( Boolean );
    const shown = this.rollup.rows.filter( ( row ) => {
      if ( this.tag && !row.hashtags.toLowerCase().split( /\s+/ ).includes( this.tag ) ) return false;
      if ( !words.length ) return true;
      const hay = ( row.title + " " + row.hashtags + " " + Object.values( row.parts ).join( " " ) ).toLowerCase();
      return words.every( ( w ) => hay.includes( w ) );
    } );
    this.table.rows( shown );
    Nav.summary( "summaries" , I18n.get( "summaries.count" ).replace( "{n}" , shown.length.toLocaleString() ).replace( "{total}" , this.rollup.rows.length.toLocaleString() ) );
  },

  // -- the Paper screen -----------------------------------------------------------------

  showPaper( key ) {
    this.paperKey = key;
    this.loadPaper();
  },

  async loadPaper() {
    const key = this.paperKey;
    let answer;
    try {
      answer = await Api.request( "/api/summaries/paper?key=" + encodeURIComponent( key ) );
    } catch ( error ) {
      return;
    }
    if ( key !== this.paperKey ) return;
    const holder = Dom.get( "paper-summaries" );
    Dom.clear( holder );
    const found = answer.summaries;
    const order = this.sections.map( ( [ k ] ) => k ).filter( ( k ) => found[ k ] );
    const note = Dom.get( "paper-summaries-note" );
    Dom.text( note , order.length ? "" : I18n.get( this.status.provider ? "summaries.none_yet" : "summaries.no_model" ) );
    Dom.show( note , !order.length );
    order.forEach( ( section , index ) => {
      const entry = found[ section ];
      const id = "paper-summary-" + section;
      const name = ( this.sections.find( ( [ k ] ) => k === section ) || [ section , section ] )[ 1 ];
      const state = entry.state || "done";
      const badges = [ Dom.el( "span" , { text: name } ) ];
      if ( state !== "done" ) badges.push( Dom.badge( I18n.get( "summaries.state_" + state ) , state === "failed" ? "danger" : "secondary" ) );
      const button = Dom.el( "button" , {
        class: "accordion-button gap-2" + ( index === 0 ? "" : " collapsed" ),
        attrs: { type: "button" , "data-bs-toggle": "collapse" , "data-bs-target": "#" + id + "-body" , "aria-expanded": String( index === 0 ) , "aria-controls": id + "-body" },
        children: badges,
      } );
      const body = Dom.el( "div" , { class: "accordion-body" } );
      if ( entry.error ) body.appendChild( Dom.el( "p" , { class: "text-danger small" , text: entry.error } ) );
      if ( entry.hashtags ) body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: entry.hashtags } ) );
      if ( entry.summary ) body.appendChild( this.markdown( entry.summary ) );
      if ( entry.model ) {
        const foot = Dom.el( "p" , { class: "small text-body-secondary mb-0 d-flex flex-wrap gap-2 align-items-center" , children: [
          Dom.el( "span" , { text: I18n.get( "summaries.made_by" ).replace( "{model}" , entry.model ) } ),
          entry.at ? Dom.when( new Date( entry.at * 1000 ).toISOString() ) : Dom.el( "span" ),
          Dom.el( "button" , { class: "btn btn-link btn-sm p-0" , text: I18n.get( "summaries.redo" ) , attrs: { type: "button" } ,
            on: { click: () => this.request( [ key ] , [ section ] , true ) } } ),
          Dom.el( "button" , { class: "btn btn-link btn-sm p-0 text-danger" , text: I18n.get( "summaries.delete" ) , attrs: { type: "button" } ,
            on: { click: () => this.remove( key , section ) } } ),
        ] } );
        body.appendChild( foot );
      }
      holder.appendChild( Dom.el( "div" , { class: "accordion-item" , children: [
        Dom.el( "h4" , { class: "accordion-header" , children: [ button ] } ),
        Dom.el( "div" , { class: "accordion-collapse collapse" + ( index === 0 ? " show" : "" ) , attrs: { id: id + "-body" } , children: [ body ] } ),
      ] } ) );
    } );
  },

  // The few Markdown shapes the summaries use: "**Heading.**" lines, "- " or
  // "* " bullets, **bold** inside a line, paragraphs. Built as nodes, never
  // as HTML, so nothing a model writes can run.
  markdown( text ) {
    const out = Dom.el( "div" , { class: "summary-text" } );
    let list = null;
    const inline = ( line ) => {
      const node = Dom.el( "span" );
      line.split( /(\*\*[^*]+\*\*)/ ).forEach( ( part ) => {
        if ( /^\*\*[^*]+\*\*$/.test( part ) ) node.appendChild( Dom.el( "strong" , { text: part.slice( 2 , -2 ) } ) );
        else if ( part ) node.appendChild( document.createTextNode( part ) );
      } );
      return node;
    };
    text.split( "\n" ).forEach( ( raw ) => {
      const line = raw.trim();
      if ( !line ) {
        list = null;
        return;
      }
      const heading = /^\*\*([^*]+)\*\*$/.exec( line ) || /^#{1,6}\s+(.*)$/.exec( line );
      if ( heading ) {
        list = null;
        out.appendChild( Dom.el( "h5" , { class: "h6 mt-3 mb-1" , text: heading[ 1 ] } ) );
        return;
      }
      const bullet = /^(?:[-*•]|\d+[.)])\s+(.*)$/.exec( line );
      if ( bullet ) {
        if ( !list ) {
          list = Dom.el( "ul" , { class: "mb-2" } );
          out.appendChild( list );
        }
        list.appendChild( Dom.el( "li" , { children: [ inline( bullet[ 1 ] ) ] } ) );
        return;
      }
      list = null;
      out.appendChild( Dom.el( "p" , { class: "mb-2" , children: [ inline( line ) ] } ) );
    } );
    return out;
  },

  summarizePaper() {
    const section = Dom.get( "paper-summary-section" ).value;
    return this.request( [ this.paperKey ] , [ section ] , false );
  },

  async remove( key , section ) {
    let old = null;
    try {
      await Undo.run( {
        label: I18n.get( "summaries.undo_delete" ),
        do: async () => {
          old = ( await Api.post( "/api/summaries/delete" , { key: key , section: section } ) ).summary;
          this.loadPaper();
        },
        undo: async () => {
          await Api.post( "/api/summaries/put" , { key: key , section: section , summary: old } );
          this.loadPaper();
        },
      } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  // -- asking -----------------------------------------------------------------------------

  ask( keys , what ) {
    if ( !keys.length ) return;
    this.asking = keys;
    Dom.text( Dom.get( "summarize-what" ) , what );
    const holder = Dom.get( "summarize-sections" );
    Dom.clear( holder );
    this.sections.forEach( ( [ key , name ] ) => {
      const id = "summarize-section-" + key;
      const box = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: id , value: key } } );
      box.checked = key === "methods";
      holder.appendChild( Dom.el( "div" , { class: "col" , children: [ Dom.el( "div" , { class: "form-check" , children: [ box , Dom.el( "label" , { class: "form-check-label" , text: name , attrs: { for: id } } ) ] } ) ] } ) );
    } );
    Dom.get( "summarize-force" ).checked = false;
    const s = this.status;
    Dom.text( Dom.get( "summarize-model" ) , s.provider ? I18n.get( "summaries.cost_note" ).replace( "{provider}" , s.provider ).replace( "{model}" , s.model ) : I18n.get( "summaries.no_model" ) );
    bootstrap.Modal.getOrCreateInstance( Dom.get( "summarize-dialog" ) ).show();
  },

  async queue() {
    const sections = Dom.all( "#summarize-sections input:checked" ).map( ( box ) => box.value );
    if ( !sections.length ) {
      Dom.toast( I18n.get( "summaries.pick_section" ) , "error" );
      return;
    }
    await this.request( this.asking || [] , sections , Dom.get( "summarize-force" ).checked );
    bootstrap.Modal.getOrCreateInstance( Dom.get( "summarize-dialog" ) ).hide();
  },

  async request( keys , sections , force ) {
    let answer;
    try {
      answer = await Api.post( "/api/summaries" , { keys: keys , sections: sections , force: force } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    Dom.toast( I18n.get( "summaries.queued" ).replace( "{queued}" , answer.queued ).replace( "{kept}" , answer.kept ) , "success" );
    this.loadStatus();
    if ( keys.includes( this.paperKey ) ) this.loadPaper();
  },
};
