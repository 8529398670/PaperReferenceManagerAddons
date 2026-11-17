// The Screener rules page (admins): every rule the review screener uses
// -- its word lists, thresholds, task categories, exclusions, extraction
// fields and datasets -- shown and editable, with a panel to try them on a
// paper before saving (/api/review/setups, app/routes/review.py).
//
// Rules come in named setups; one is in use. The picker shows any setup, and
// the page edits a copy of its rules (draft). Each edit is checked on the
// server a moment later (every pattern compiles, every value has the right
// type), and a field the check names turns red. Save keeps the whole draft;
// saving the setup in use re-screens each candidate paper in the background,
// which the progress line follows. Use switches the setup in use. Reset takes
// the default setup back to config/review.yaml.
//
// Labels and help for the word lists and thresholds come from the rules
// themselves (config/review.yaml), so a new threshold needs no change here.
const ReviewRules = {
  snap: null,
  draft: null,
  setupId: "",
  setups: [],
  dialogMode: "",
  tab: "criteria",
  problems: [],
  rescreen: 0,
  checkedSig: "",
  testKey: "",
  testTicket: 0,
  tabs: [ "criteria" , "thresholds" , "tasks" , "exclusions" , "fields" , "datasets" , "missing" ],

  init( me ) {
    if ( me.role !== "admin" ) return;
    Dom.show( Dom.get( "review-rules-panel" ) , true );
    this.setupId = this.remembered( "review-rules-setup" , "" );
    Dom.get( "rr-setup" ).addEventListener( "change" , ( event ) => this.pickSetup( event.target.value ) );
    Dom.onPress( Dom.get( "rr-use" ) , () => this.use() );
    Dom.onPress( Dom.get( "rr-new" ) , () => this.openDialog( "new" ) );
    Dom.onPress( Dom.get( "rr-rename" ) , () => this.openDialog( "rename" ) );
    Dom.onPress( Dom.get( "rr-delete" ) , () => this.remove() );
    Dom.get( "rr-setup-form" ).addEventListener( "submit" , ( event ) => { event.preventDefault(); this.submitDialog(); } );
    this.tab = this.savedTab();
    this.drawTabs();
    Dom.onPress( Dom.get( "rr-save" ) , () => this.save() );
    Dom.onPress( Dom.get( "rr-discard" ) , () => this.discard() );
    Dom.onPress( Dom.get( "rr-reset" ) , () => this.reset() );
    Dom.onPress( Dom.get( "rr-test-run" ) , () => this.test() );
    Dom.get( "rr-test-paste" ).addEventListener( "change" , ( event ) => {
      Dom.show( Dom.get( "rr-test-pick" ) , !event.target.checked );
      Dom.show( Dom.get( "rr-test-text" ) , event.target.checked );
    } );
    Dom.typed( Dom.get( "rr-test-search" ) , () => this.search() , 250 );
    this.checkSoon = Content.throttle( () => this.check() , 600 );
    const progress = Content.throttle( () => this.loadProgress() , 4000 );
    Content.on( "queue" , () => { if ( Nav.current() === "review-rules" ) progress(); } );
    window.addEventListener( "hashchange" , () => {
      if ( Nav.current() === "review-rules" && !this.snap ) this.load();
    } );
    window.addEventListener( "beforeunload" , ( event ) => {
      if ( this.dirty() ) event.preventDefault();
    } );
    if ( Nav.current() === "review-rules" ) this.load();
  },

  t( key , values ) {
    let text = I18n.get( "review_rules." + key );
    Object.entries( values || {} ).forEach( ( [ name , value ] ) => {
      text = text.replace( "{" + name + "}" , () => String( value ) );
    } );
    return text;
  },

  remembered( name , fallback ) {
    try {
      return window.localStorage.getItem( name ) || fallback;
    } catch ( error ) {
      return fallback;
    }
  },

  remember( name , value ) {
    try {
      window.localStorage.setItem( name , value );
    } catch ( error ) {
      // Remembering is a nicety.
    }
  },

  url( tail ) {
    return "/api/review/setups/" + encodeURIComponent( this.setupId ) + ( tail || "" );
  },

  active() {
    return !!this.snap && this.snap.in_use === this.setupId;
  },

  setupName( setup ) {
    return setup.builtin ? this.t( "default_name" ) : setup.name;
  },

  inUseName() {
    const found = this.setups.find( ( setup ) => setup.active );
    return found ? this.setupName( found ) : "";
  },

  savedTab() {
    try {
      const tab = window.localStorage.getItem( "review-rules-tab" );
      return this.tabs.includes( tab ) ? tab : "criteria";
    } catch ( error ) {
      return "criteria";
    }
  },

  // ---- loading and saving ---------------------------------------------------------

  async load() {
    let snap;
    try {
      const listing = await Api.request( "/api/review/setups" );
      this.setups = listing.setups;
      if ( !this.setups.some( ( setup ) => setup.id === this.setupId ) ) this.setupId = listing.in_use;
      snap = await Api.request( this.url() );
    } catch ( error ) {
      App.showError( error.message );
      return;
    }
    this.showSetup( snap );
  },

  async loadSetups() {
    try {
      this.setups = ( await Api.request( "/api/review/setups" ) ).setups;
    } catch ( error ) {
      // The picker keeps what it had.
    }
    this.drawSetups();
  },

  // A setup's rules arrived: draw them as they are kept.
  showSetup( snap ) {
    this.snap = snap;
    this.setupId = snap.setup.id;
    this.remember( "review-rules-setup" , this.setupId );
    this.draft = JSON.parse( JSON.stringify( snap.rules ) );
    this.problems = [];
    this.rescreen = 0;
    this.checkedSig = snap.signature;
    this.drawSetups();
    this.drawHeader();
    this.drawBody();
  },

  async pickSetup( setup ) {
    if ( setup === this.setupId ) return;
    if ( this.dirty() && !( await Dom.confirm( this.t( "switch_confirm" ) ) ) ) {
      Dom.get( "rr-setup" ).value = this.setupId;
      return;
    }
    this.setupId = setup;
    let snap;
    try {
      snap = await Api.request( this.url() );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      await this.load();
      return;
    }
    this.showSetup( snap );
  },

  async use() {
    if ( this.dirty() ) {
      Dom.toast( this.t( "use_dirty" ) , "error" );
      return;
    }
    try {
      this.showSetup( await Api.post( this.url( "/activate" ) , {} ) );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    await this.loadSetups();
    Dom.toast( this.t( "now_in_use" , { name: this.inUseName() } ) , "ok" );
  },

  async remove() {
    const name = this.setupName( this.snap.setup );
    if ( !( await Dom.confirm( this.t( "delete_confirm" , { name: name } ) ) ) ) return;
    try {
      await Api.post( this.url( "/delete" ) , {} );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.setupId = this.snap.in_use;
    Dom.toast( this.t( "deleted" ) , "ok" );
    await this.load();
  },

  openDialog( mode ) {
    this.dialogMode = mode;
    const setup = this.snap.setup;
    Dom.text( Dom.get( "rr-setup-heading" ) , this.t( mode === "new" ? "new_heading" : "rename_heading" ) );
    Dom.text( Dom.get( "rr-setup-submit" ) , this.t( mode === "new" ? "create" : "rename_save" ) );
    Dom.text( Dom.get( "rr-setup-from" ) , mode === "new" ? this.t( "new_from" , { name: this.setupName( setup ) } ) : "" );
    Dom.show( Dom.get( "rr-setup-from" ) , mode === "new" );
    Dom.get( "rr-setup-name" ).value = mode === "new" ? "" : setup.name;
    Dom.get( "rr-setup-about" ).value = mode === "new" ? "" : setup.description;
    const element = Dom.get( "rr-setup-dialog" );
    element.addEventListener( "shown.bs.modal" , () => Dom.get( "rr-setup-name" ).focus() , { once: true } );
    bootstrap.Modal.getOrCreateInstance( element ).show();
  },

  async submitDialog() {
    const name = Dom.get( "rr-setup-name" ).value.trim();
    const description = Dom.get( "rr-setup-about" ).value.trim();
    if ( !name ) return;
    let snap;
    try {
      if ( this.dialogMode === "new" ) {
        const body = { name: name , description: description , source: this.setupId };
        if ( this.dirty() ) body.rules = this.draft;
        snap = await Api.post( "/api/review/setups" , body );
      } else {
        snap = await Api.post( this.url() , { name: name , description: description , base_signature: this.snap.signature } );
      }
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    bootstrap.Modal.getOrCreateInstance( Dom.get( "rr-setup-dialog" ) ).hide();
    if ( this.dialogMode === "new" ) {
      this.setupId = snap.setup.id;
      this.showSetup( snap );
      Dom.toast( this.t( "created" ) , "ok" );
    } else {
      // A rename keeps the rules, and any changes not saved yet.
      const draft = this.draft;
      this.showSetup( snap );
      this.draft = draft;
      this.drawHeader();
      this.drawBody();
    }
    await this.loadSetups();
  },

  async loadProgress() {
    if ( !this.snap ) return;
    try {
      const answer = await Api.request( "/api/review/progress" );
      this.snap.progress = answer.progress;
      this.drawProgress();
    } catch ( error ) {
      // The next queue event tries again.
    }
  },

  dirty() {
    return !!this.snap && JSON.stringify( this.draft ) !== JSON.stringify( this.snap.rules );
  },

  async save() {
    const before = this.snap.signature;
    const active = this.active();
    try {
      this.snap = await Api.post( this.url() , { rules: this.draft , base_signature: before } );
    } catch ( error ) {
      if ( error.payload && error.payload.problems ) {
        this.problems = error.payload.problems;
        this.markProblems();
      }
      if ( error.payload && error.payload.error === "review_rules_moved" ) {
        if ( await Dom.confirm( this.t( "moved" ) ) ) await this.load();
        return;
      }
      Dom.toast( error.message , "error" );
      return;
    }
    this.draft = JSON.parse( JSON.stringify( this.snap.rules ) );
    this.problems = [];
    this.rescreen = 0;
    Dom.toast( this.t( this.snap.signature === before ? "saved_same" : active ? "saved" : "saved_unused" ) , "ok" );
    this.checkedSig = this.snap.signature;
    this.drawHeader();
    this.drawBody();
    this.loadSetups();
  },

  async discard() {
    if ( !( await Dom.confirm( this.t( "discard_confirm" ) ) ) ) return;
    this.draft = JSON.parse( JSON.stringify( this.snap.rules ) );
    this.problems = [];
    this.rescreen = 0;
    this.drawHeader();
    this.drawBody();
  },

  async reset() {
    if ( !( await Dom.confirm( this.t( "reset_confirm" ) ) ) ) return;
    try {
      this.snap = await Api.post( this.url( "/reset" ) , {} );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.draft = JSON.parse( JSON.stringify( this.snap.rules ) );
    this.problems = [];
    this.rescreen = 0;
    Dom.toast( this.t( "reset_done" ) , "ok" );
    this.drawHeader();
    this.drawBody();
    this.loadSetups();
  },

  // Something was typed: mark what differs from the defaults, and ask the
  // server whether the rules still load.
  edited() {
    this.drawHeader();
    this.checkSoon();
  },

  async check() {
    if ( !this.dirty() ) {
      this.problems = [];
      this.rescreen = 0;
      this.markProblems();
      this.drawHeader();
      return;
    }
    try {
      const answer = await Api.post( "/api/review/check" , { rules: this.draft } );
      this.problems = answer.problems;
      this.rescreen = !this.active() || answer.signature === this.snap.signature ? 0 : answer.rescreen;
    } catch ( error ) {
      return;
    }
    this.markProblems();
    this.drawHeader();
  },

  // ---- the header: the setups, progress, who saved, the buttons --------------------

  drawSetups() {
    const select = Dom.get( "rr-setup" );
    Dom.clear( select );
    this.setups.forEach( ( setup ) => {
      const name = this.setupName( setup );
      select.appendChild( Dom.el( "option" , {
        text: setup.active ? this.t( "setup_in_use" , { name: name } ) : name,
        attrs: Object.assign( { value: setup.id } , setup.id === this.setupId ? { selected: "selected" } : {} ),
      } ) );
    } );
    select.value = this.setupId;
  },

  drawHeader() {
    if ( !this.snap ) return;
    this.drawProgress();
    const edited = Dom.get( "rr-edited" );
    if ( this.snap.edited && this.snap.updated_at ) {
      const when = this.snap.updated_at ? Dom.ago( new Date( this.snap.updated_at * 1000 ) ) : "";
      Dom.text( edited , this.t( "edited_by" , { who: this.snap.updated_by || "?" , when: when } ) );
    } else {
      Dom.text( edited , this.t( "using_defaults" ) );
    }
    const dirty = this.dirty();
    const setup = this.snap.setup;
    const active = this.active();
    const use = Dom.get( "rr-use" );
    use.disabled = active;
    use.title = dirty && !active ? this.t( "use_dirty" ) : "";
    Dom.get( "rr-rename" ).disabled = setup.builtin;
    Dom.get( "rr-delete" ).disabled = setup.builtin || active;
    Dom.show( Dom.get( "rr-reset" ) , setup.builtin );
    const about = Dom.get( "rr-setup-description" );
    Dom.text( about , setup.description || "" );
    Dom.show( about , !!setup.description );
    const note = Dom.get( "rr-setup-note" );
    Dom.text( note , active ? "" : this.t( "not_in_use" , { name: this.inUseName() } ) );
    Dom.show( note , !active );
    const exportLink = Dom.get( "rr-export" );
    exportLink.href = this.url( "/export" );
    exportLink.setAttribute( "download" , setup.builtin ? "review.yaml" : "review-" + setup.id + ".yaml" );
    const save = Dom.get( "rr-save" );
    save.disabled = !dirty || this.problems.length > 0;
    Dom.text( Dom.get( "rr-save-text" ) , dirty && this.rescreen ? this.t( "save_rescreen" , { n: this.rescreen } ) : this.t( "save" ) );
    Dom.get( "rr-discard" ).disabled = !dirty;
    Dom.get( "rr-reset" ).disabled = !this.snap.edited;
    const problem = Dom.get( "rr-problem" );
    Dom.text( problem , this.snap.problem || "" );
    Dom.show( problem , !!this.snap.problem );
    const box = Dom.get( "rr-problems" );
    Dom.clear( box );
    if ( this.problems.length ) {
      box.appendChild( Dom.el( "p" , { class: "mb-1 fw-semibold" , text: this.t( "problems" ) } ) );
      box.appendChild( Dom.el( "ul" , {
        class: "mb-0 small",
        children: this.problems.slice( 0 , 30 ).map( ( p ) => Dom.el( "li" , {
          children: [ Dom.el( "code" , { text: p.path } ) , document.createTextNode( " " + p.message ) ],
        } ) ),
      } ) );
    }
    Dom.show( box , this.problems.length > 0 );
  },

  drawProgress() {
    const p = this.snap.progress;
    const box = Dom.get( "rr-progress" );
    Dom.clear( box );
    const parts = [ this.active()
      ? this.t( "progress" , { current: p.current , candidates: p.candidates } )
      : this.t( "progress_in_use" , { current: p.current , candidates: p.candidates , name: this.inUseName() } ) ];
    if ( p.waiting ) parts.push( this.t( "progress_waiting" , { waiting: p.waiting } ) );
    if ( p.failed ) parts.push( this.t( "progress_failed" , { failed: p.failed } ) );
    parts.push( this.t( "progress_verdicts" , { included: p.included , borderline: p.borderline } ) );
    if ( p.waiting ) box.appendChild( Dom.el( "span" , { class: "spinner-border spinner-border-sm me-2" , attrs: { "aria-hidden": "true" } } ) );
    box.appendChild( document.createTextNode( parts.join( " · " ) ) );
    if ( this.dirty() ) box.appendChild( Dom.el( "span" , { class: "badge text-bg-warning ms-2" , text: this.t( "unsaved" ) } ) );
  },

  // ---- tabs ---------------------------------------------------------------------------

  drawTabs() {
    const list = Dom.get( "rr-tabs" );
    Dom.clear( list );
    this.tabs.forEach( ( tab ) => {
      const link = Dom.el( "a" , {
        class: "nav-link" + ( tab === this.tab ? " active" : "" ),
        text: this.t( "tab_" + tab ),
        attrs: Object.assign( { href: "#review-rules" , "data-rr-tab": tab } , tab === this.tab ? { "aria-current": "true" } : {} ),
        on: { click: ( event ) => { event.preventDefault(); this.show( tab ); } },
      } );
      list.appendChild( Dom.el( "li" , { class: "nav-item" , children: [ link ] } ) );
    } );
  },

  show( tab ) {
    this.tab = tab;
    try {
      window.localStorage.setItem( "review-rules-tab" , tab );
    } catch ( error ) {
      // Remembering the tab is a nicety.
    }
    this.drawTabs();
    this.drawBody();
  },

  drawBody() {
    const body = Dom.get( "rr-body" );
    Dom.clear( body );
    if ( !this.draft ) return;
    const draw = {
      criteria: () => this.drawCriteria( body ),
      thresholds: () => this.drawThresholds( body ),
      tasks: () => this.drawTasks( body ),
      exclusions: () => this.drawExclusions( body ),
      fields: () => this.drawFields( body ),
      datasets: () => this.drawDatasets( body ),
      missing: () => this.drawMissing( body ),
    }[ this.tab ];
    draw();
    this.markProblems();
  },

  // ---- defaults, changes and problems -------------------------------------------------

  // The default at a path like [ "extraction" , "fields" , "@TR" , "patterns" ]:
  // "@name" picks the list item with that name.
  defaultAt( path ) {
    let node = this.snap.defaults;
    for ( const step of path ) {
      if ( node == null ) return undefined;
      if ( typeof step === "string" && step.startsWith( "@" ) ) node = ( node || [] ).find( ( item ) => item.name === step.slice( 1 ) );
      else node = node[ step ];
    }
    return node;
  },

  differs( value , path ) {
    const fallback = this.defaultAt( path );
    return JSON.stringify( value ) !== JSON.stringify( fallback );
  },

  // A "changed" badge with a button that puts the default back.
  changedMark( value , path , restore ) {
    const holder = Dom.el( "span" , { class: "ms-2 rr-changed" } );
    const paint = () => {
      Dom.clear( holder );
      if ( !this.differs( value() , path ) ) return;
      const fallback = this.defaultAt( path );
      holder.appendChild( Dom.el( "span" , { class: "badge text-bg-warning" , text: this.t( "changed" ) } ) );
      if ( fallback !== undefined ) {
        holder.appendChild( Dom.el( "button" , {
          class: "btn btn-link btn-sm py-0",
          attrs: { type: "button" , title: this.t( "revert" ) },
          children: [ Dom.el( "i" , { class: "bi bi-arrow-counterclockwise" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { class: "visually-hidden" , text: this.t( "revert" ) } ) ],
          on: { click: () => { restore( JSON.parse( JSON.stringify( fallback ) ) ); this.edited(); this.drawBody(); } },
        } ) );
      }
    };
    paint();
    holder.repaint = paint;
    return holder;
  },

  // Turn the inputs a problem names red, with its message under them.
  markProblems() {
    Dom.all( "#rr-body [data-path], #rr-editor-body [data-path]" ).forEach( ( input ) => {
      input.classList.remove( "is-invalid" );
      const note = input.parentElement && input.parentElement.querySelector( ":scope > .invalid-feedback" );
      if ( note ) note.remove();
    } );
    this.problems.forEach( ( problem ) => {
      Dom.all( "[data-path]" ).filter( ( input ) => input.getAttribute( "data-path" ) === problem.path ).forEach( ( input ) => {
        input.classList.add( "is-invalid" );
        input.after( Dom.el( "div" , { class: "invalid-feedback" , text: problem.message } ) );
      } );
    } );
  },

  // ---- building blocks -------------------------------------------------------------------

  card( title , help , extras , children ) {
    const head = Dom.el( "div" , { class: "d-flex flex-wrap align-items-center" , children: [ Dom.el( "h4" , { class: "h6 mb-0" , text: title } ) ].concat( extras || [] ) } );
    const kids = [ head ];
    if ( help ) kids.push( Dom.el( "p" , { class: "small text-body-secondary mt-1 mb-2" , text: help } ) );
    return Dom.el( "div" , { class: "col" , children: [ Dom.el( "div" , { class: "border rounded p-2 p-md-3 h-100" , children: kids.concat( children ) } ) ] } );
  },

  input( value , onInput , options ) {
    const settings = options || {};
    const node = Dom.el( settings.area ? "textarea" : "input" , {
      class: "form-control" + ( settings.small === false ? "" : " form-control-sm" ) + ( settings.mono ? " font-monospace" : "" ),
      attrs: Object.assign( settings.area ? { rows: String( settings.rows || 3 ) } : { type: settings.type || "text" } ,
        settings.path ? { "data-path": settings.path } : {} , settings.label ? { "aria-label": settings.label } : {} ,
        settings.step ? { step: settings.step } : {} , { spellcheck: "false" } ),
    } );
    node.value = value == null ? "" : String( value );
    node.addEventListener( "input" , () => onInput( node.value , node ) );
    return node;
  },

  // An editable list of regular expressions. arr is changed in place.
  patterns( arr , path , pathText , redraw ) {
    const list = Dom.el( "div" , { class: "d-flex flex-column gap-1" } );
    const draw = () => {
      Dom.clear( list );
      arr.forEach( ( pattern , i ) => {
        // A long pattern wraps in a text box (a pattern is one line, so a
        // typed newline is dropped).
        const long = ( pattern || "" ).length > 60;
        const input = this.input( pattern , ( value , node ) => {
          if ( value.includes( "\n" ) ) {
            value = value.replace( /\n/g , "" );
            node.value = value;
          }
          arr[ i ] = value;
          this.edited();
          if ( redraw ) redraw();
        } , {
          mono: true, path: pathText + "[" + i + "]", label: this.t( "pattern_label" , { n: i + 1 } ),
          area: long, rows: long ? Math.min( 6 , Math.ceil( pattern.length / 55 ) ) : 1,
        } );
        const remove = Dom.el( "button" , {
          class: "btn btn-outline-secondary btn-sm",
          attrs: { type: "button" , title: this.t( "remove_pattern" ) },
          children: [ Dom.el( "i" , { class: "bi bi-x-lg" , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { class: "visually-hidden" , text: this.t( "remove_pattern" ) } ) ],
          on: { click: () => { arr.splice( i , 1 ); this.edited(); draw(); if ( redraw ) redraw(); this.markProblems(); } },
        } );
        list.appendChild( Dom.el( "div" , { class: "input-group input-group-sm has-validation" , children: [ input , remove ] } ) );
      } );
      list.appendChild( Dom.el( "div" , { children: [ Dom.el( "button" , {
        class: "btn btn-outline-primary btn-sm",
        attrs: { type: "button" },
        children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , document.createTextNode( " " + this.t( "add_pattern" ) ) ],
        on: { click: () => {
          arr.push( "" );
          draw();
          if ( redraw ) redraw();
          const inputs = list.querySelectorAll( "input" );
          if ( inputs.length ) inputs[ inputs.length - 1 ].focus();
        } },
      } ) ] } ) );
    };
    draw();
    return list;
  },

  // A card for one word list: { label, help, patterns }.
  vocabCard( name ) {
    const vocab = this.draft.vocab[ name ];
    const path = [ "vocab" , name , "patterns" ];
    let mark;
    const repaint = () => mark.repaint();
    mark = this.changedMark( () => vocab.patterns , path , ( value ) => { vocab.patterns = value; } );
    const count = Dom.el( "span" , { class: "badge text-bg-light border ms-2" , text: this.t( "patterns_count" , { n: vocab.patterns.length } ) } );
    return this.card( vocab.label , vocab.help , [ count , mark ] , [ this.patterns( vocab.patterns , path , "vocab." + name + ".patterns" , () => {
      repaint();
      Dom.text( count , this.t( "patterns_count" , { n: vocab.patterns.length } ) );
    } ) ] );
  },

  // A table of thresholds: { name: { value, why } }.
  thresholdTable( block , path , pathText ) {
    const rows = Object.keys( block ).map( ( name ) => {
      const item = block[ name ];
      const fallback = this.defaultAt( path.concat( [ name , "value" ] ) );
      let mark;
      const input = this.input( item.value , ( value ) => {
        item.value = value === "" ? value : Number( value );
        mark.repaint();
        this.edited();
      } , { type: "number" , step: "any" , path: pathText + "." + name + ".value" , label: name } );
      input.classList.add( "rr-number" );
      mark = this.changedMark( () => item.value , path.concat( [ name , "value" ] ) , ( value ) => { item.value = value; } );
      return Dom.el( "tr" , { children: [
        Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: name } ) ] } ),
        Dom.el( "td" , { children: [ input ] } ),
        Dom.el( "td" , { class: "small" , children: [
          document.createTextNode( item.why || "" ),
          Dom.el( "div" , { class: "text-body-secondary" , children: [ document.createTextNode( fallback !== undefined ? this.t( "default_value" , { value: fallback } ) : "" ) , mark ] } ),
        ] } ),
      ] } );
    } );
    const head = Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: [
      Dom.el( "th" , { attrs: { scope: "col" } , text: this.t( "col_rule" ) } ),
      Dom.el( "th" , { class: "rr-col-value" , attrs: { scope: "col" } , text: this.t( "col_value" ) } ),
      Dom.el( "th" , { attrs: { scope: "col" } , text: this.t( "col_why" ) } ),
    ] } ) ] } );
    return Dom.el( "div" , { class: "table-responsive" , children: [
      Dom.el( "table" , { class: "table table-sm align-middle mb-0" , children: [ head , Dom.el( "tbody" , { children: rows } ) ] } ),
    ] } );
  },

  grid( children , cols ) {
    return Dom.el( "div" , { class: "row g-3 " + ( cols || "row-cols-1 row-cols-lg-2" ) , children: children } );
  },

  section( title , help , children ) {
    const kids = [ Dom.el( "h4" , { class: "h6 mt-3 mb-1" , text: title } ) ];
    if ( help ) kids.push( Dom.el( "p" , { class: "small text-body-secondary mb-2" , text: help } ) );
    return Dom.el( "div" , { children: kids.concat( children ) } );
  },

  iconButton( icon , label , onClick , tone ) {
    return Dom.el( "button" , {
      class: "btn btn-sm " + ( tone || "btn-outline-secondary" ),
      attrs: { type: "button" , title: label },
      children: [ Dom.el( "i" , { class: "bi bi-" + icon , attrs: { "aria-hidden": "true" } } ) , Dom.el( "span" , { class: "visually-hidden" , text: label } ) ],
      on: { click: onClick },
    } );
  },

  // ---- the tabs' contents ------------------------------------------------------------------

  drawCriteria( body ) {
    const texts = [];
    [ "full" , "abstract" ].forEach( ( kind ) => {
      const list = this.draft.criteria_text[ kind ];
      texts.push( this.card( this.t( "criteria_" + kind ) , "" , [ this.changedMark( () => list , [ "criteria_text" , kind ] , ( value ) => { this.draft.criteria_text[ kind ] = value; } ) ] ,
        list.map( ( text , i ) => Dom.el( "div" , { class: "mb-2" , children: [ this.input( text , ( value ) => { list[ i ] = value; this.edited(); } , {
          area: true, rows: 3, path: "criteria_text." + kind + "[" + i + "]", label: ( i + 1 ) + ".",
        } ) ] } ) ) ) );
    } );
    body.appendChild( this.section( this.t( "criteria_heading" ) , this.t( "criteria_help" ) , [ this.grid( texts ) ] ) );
    body.appendChild( this.section( this.t( "vocab_heading" ) , this.t( "vocab_help" ) ,
      [ this.grid( this.snap.vocab_names.map( ( name ) => this.vocabCard( name ) ) ) ] ) );
    const survey = this.draft.survey_title;
    const surveyInput = this.input( survey.pattern , ( value ) => { survey.pattern = value; this.edited(); } , { mono: true , path: "survey_title.pattern" , label: this.t( "survey_heading" ) } );
    const roleCards = this.draft.attention_roles.map( ( role , i ) => {
      const path = [ "attention_roles" , i ];
      if ( role.use_vocab ) {
        const vocab = this.draft.vocab[ role.use_vocab ];
        return this.card( role.label , this.t( "role_uses" , { name: vocab ? vocab.label : role.use_vocab } ) , [] , [] );
      }
      return this.card( role.label , "" , [ this.changedMark( () => role.patterns , path.concat( [ "patterns" ] ) , ( value ) => { role.patterns = value; } ) ] ,
        [ this.patterns( role.patterns , path.concat( [ "patterns" ] ) , "attention_roles[" + i + "].patterns" ) ] );
    } );
    body.appendChild( this.section( this.t( "survey_heading" ) , survey.help , [ surveyInput ] ) );
    body.appendChild( this.section( this.t( "roles_heading" ) , this.t( "roles_help" ) , [ this.grid( roleCards , "row-cols-1 row-cols-md-2 row-cols-xxl-3" ) ] ) );
  },

  drawThresholds( body ) {
    body.appendChild( this.section( this.t( "thresholds_full" ) , this.t( "thresholds_full_help" ) ,
      [ this.thresholdTable( this.draft.thresholds.full , [ "thresholds" , "full" ] , "thresholds.full" ) ] ) );
    body.appendChild( this.section( this.t( "thresholds_abstract" ) , this.t( "thresholds_abstract_help" ) ,
      [ this.thresholdTable( this.draft.thresholds.abstract , [ "thresholds" , "abstract" ] , "thresholds.abstract" ) ] ) );
  },

  drawTasks( body ) {
    const tasks = this.draft.tasks;
    const unclassified = this.input( this.draft.unclassified_priority , ( value ) => {
      this.draft.unclassified_priority = Number( value );
      this.edited();
    } , { type: "number" , path: "unclassified_priority" , label: this.t( "unclassified_priority" ) } );
    unclassified.classList.add( "rr-number" );
    body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "tasks_help" ) } ) );
    body.appendChild( Dom.el( "div" , { class: "row g-2 align-items-center mb-3" , children: [
      Dom.el( "div" , { class: "col-auto" , children: [ Dom.el( "label" , { class: "col-form-label small" , text: this.t( "unclassified_priority" ) } ) ] } ),
      Dom.el( "div" , { class: "col-auto" , children: [ unclassified ] } ),
    ] } ) );
    const cards = tasks.map( ( task , i ) => {
      const path = [ "tasks" , "@" + task.name ];
      const name = this.input( task.name , ( value ) => { task.name = value; this.edited(); } , { path: "tasks[" + i + "].name" , label: this.t( "task_name" ) } );
      const priority = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { "aria-label": this.t( "task_priority" ) , "data-path": "tasks[" + i + "].priority" } ,
        children: [ 1 , 2 , 3 , 4 , 5 , 6 , 7 , 8 , 9 ].map( ( n ) => Dom.el( "option" , { text: String( n ) , attrs: { value: String( n ) } } ) ) } );
      priority.value = String( task.priority );
      priority.addEventListener( "change" , () => { task.priority = Number( priority.value ); this.edited(); } );
      const move = ( by ) => {
        const j = i + by;
        if ( j < 0 || j >= tasks.length ) return;
        [ tasks[ i ] , tasks[ j ] ] = [ tasks[ j ] , tasks[ i ] ];
        this.edited();
        this.drawBody();
      };
      const tools = Dom.el( "div" , { class: "btn-group ms-auto" , children: [
        this.iconButton( "arrow-up" , this.t( "move_up" ) , () => move( -1 ) ),
        this.iconButton( "arrow-down" , this.t( "move_down" ) , () => move( 1 ) ),
        this.iconButton( "trash" , this.t( "remove_task" ) , () => { tasks.splice( i , 1 ); this.edited(); this.drawBody(); } , "btn-outline-danger" ),
      ] } );
      const top = Dom.el( "div" , { class: "row g-2 align-items-center mb-2" , children: [
        Dom.el( "div" , { class: "col" , children: [ name ] } ),
        Dom.el( "div" , { class: "col-auto" , children: [ priority ] } ),
        Dom.el( "div" , { class: "col-12 col-sm-auto d-flex" , children: [ tools ] } ),
      ] } );
      const mark = this.changedMark( () => task , path , ( value ) => { tasks[ i ] = value; } );
      return this.card( "#" + ( i + 1 ) , "" , [ mark ] , [ top , this.patterns( task.patterns , path.concat( [ "patterns" ] ) , "tasks[" + i + "].patterns" , () => mark.repaint() ) ] );
    } );
    body.appendChild( this.grid( cards ) );
    body.appendChild( Dom.el( "button" , {
      class: "btn btn-outline-primary btn-sm mt-3", attrs: { type: "button" },
      children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , document.createTextNode( " " + this.t( "add_task" ) ) ],
      on: { click: () => { tasks.push( { name: "" , priority: 5 , patterns: [ "" ] } ); this.edited(); this.drawBody(); } },
    } ) );
  },

  drawExclusions( body ) {
    body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "exclusions_help" ) } ) );
    const cards = Object.keys( this.draft.exclusions ).map( ( name ) => {
      const rule = this.draft.exclusions[ name ];
      const path = [ "exclusions" , name ];
      const label = this.input( rule.label , ( value ) => { rule.label = value; this.edited(); } , { path: "exclusions." + name + ".label" , label: this.t( "exclusion_label" ) } );
      const mark = this.changedMark( () => rule.patterns , path.concat( [ "patterns" ] ) , ( value ) => { rule.patterns = value; } );
      return this.card( name , "" , [ mark ] , [
        Dom.el( "label" , { class: "form-label small mb-1" , text: this.t( "exclusion_label" ) } ), label,
        Dom.el( "div" , { class: "mt-2" , children: [ this.patterns( rule.patterns , path.concat( [ "patterns" ] ) , "exclusions." + name + ".patterns" , () => mark.repaint() ) ] } ),
      ] );
    } );
    body.appendChild( this.grid( cards , "row-cols-1 row-cols-xxl-3" ) );
    const reasons = this.draft.reasons;
    const rows = Object.keys( reasons ).map( ( code ) => {
      const input = this.input( reasons[ code ] , ( value ) => { reasons[ code ] = value; this.edited(); } , { path: "reasons." + code , label: code } );
      return Dom.el( "tr" , { children: [ Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: code } ) ] } ) , Dom.el( "td" , { children: [ input ] } ) ] } );
    } );
    body.appendChild( this.section( this.t( "reasons_heading" ) , this.t( "reasons_help" ) , [ Dom.el( "div" , { class: "table-responsive" , children: [
      Dom.el( "table" , { class: "table table-sm align-middle mb-0" , children: [ Dom.el( "tbody" , { children: rows } ) ] } ),
    ] } ) ] ) );
  },

  postText( post ) {
    if ( post.kind === "seconds_or_ms" ) return this.t( "kind_seconds_or_ms" );
    if ( post.kind === "negation" ) return post.template + " / " + post.value;
    return post.template + ( post.lower ? " (lower)" : "" );
  },

  rangeText( plausible ) {
    if ( !plausible ) return "";
    const parts = [];
    if ( plausible.range ) parts.push( plausible.range.join( "–" ) );
    if ( plausible.range_seconds ) parts.push( plausible.range_seconds.join( "–" ) + " s" );
    return parts.join( " · " );
  },

  drawFields( body ) {
    const ext = this.draft.extraction;
    body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "fields_help" ) } ) );
    const settings = {};
    [ "text_cap" , "context_window" , "evidence_quotes" , "evidence_chars" ].forEach( ( name ) => { settings[ name ] = ext[ name ]; } );
    const words = this.input( Object.entries( ext.word_numbers ).map( ( [ w , n ] ) => w + " = " + n ).join( "\n" ) , ( value ) => {
      const out = {};
      value.split( "\n" ).forEach( ( line ) => {
        const [ w , n ] = line.split( "=" ).map( ( s ) => ( s || "" ).trim() );
        if ( w && n !== "" && !Number.isNaN( Number( n ) ) ) out[ w ] = Number( n );
      } );
      ext.word_numbers = out;
      this.edited();
    } , { area: true , rows: 6 , mono: true , path: "extraction.word_numbers" , label: this.t( "word_numbers" ) } );
    const num = this.input( ext.macros.NUM || "" , ( value ) => { ext.macros.NUM = value; this.edited(); } , { mono: true , path: "extraction.macros.NUM" , label: this.t( "macro_num" ) } );
    body.appendChild( this.grid( [
      this.card( this.t( "fields_settings" ) , "" , [] , [ this.thresholdTable( settings , [ "extraction" ] , "extraction" ) ] ),
      this.card( this.t( "word_numbers" ) , this.t( "word_numbers_help" ) , [] , [ words , Dom.el( "label" , { class: "form-label small mt-2 mb-1" , text: this.t( "macro_num" ) } ) , num ] ),
    ] , "row-cols-1" ) );
    const rows = ext.fields.map( ( field , i ) => {
      const changed = this.differs( field , [ "extraction" , "fields" , "@" + field.name ] );
      return Dom.el( "tr" , { children: [
        Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: field.name || "?" } ) , changed ? Dom.el( "span" , { class: "badge text-bg-warning ms-2" , text: this.t( "changed" ) } ) : document.createTextNode( "" ) ] } ),
        Dom.el( "td" , { class: "small" , text: field.group } ),
        Dom.el( "td" , { class: "small text-end" , text: String( field.patterns.length ) } ),
        Dom.el( "td" , { class: "small font-monospace text-break" , text: this.postText( field.post ) } ),
        Dom.el( "td" , { class: "small text-nowrap" , text: this.rangeText( field.plausible ) } ),
        Dom.el( "td" , { class: "text-end" , children: [ Dom.el( "button" , {
          class: "btn btn-outline-secondary btn-sm", attrs: { type: "button" , "data-path": "extraction.fields[" + field.name + "]" },
          text: this.t( "edit" ), on: { click: () => this.editField( i ) },
        } ) ] } ),
      ] } );
    } );
    const head = Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: [ "col_field" , "col_group" , "col_patterns" , "col_post" , "col_plausible" ].map( ( key ) =>
      Dom.el( "th" , { attrs: { scope: "col" } , text: this.t( key ) } ) ).concat( [ Dom.el( "th" , { attrs: { scope: "col" } } ) ] ) } ) ] } );
    body.appendChild( Dom.el( "div" , { class: "table-responsive mt-3" , children: [
      Dom.el( "table" , { class: "table table-sm table-hover align-middle mb-0" , children: [ head , Dom.el( "tbody" , { children: rows } ) ] } ),
    ] } ) );
    body.appendChild( Dom.el( "button" , {
      class: "btn btn-outline-primary btn-sm mt-3", attrs: { type: "button" },
      children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , document.createTextNode( " " + this.t( "add_field" ) ) ],
      on: { click: () => {
        ext.fields.push( { name: "New_Field" , group: "Architecture" , patterns: [ "" ] , post: { kind: "template" , template: "${0}" } } );
        this.edited();
        this.drawBody();
        this.editField( ext.fields.length - 1 );
      } },
    } ) );
  },

  openEditor( title , children ) {
    Dom.text( Dom.get( "rr-editor-title" ) , title );
    const body = Dom.get( "rr-editor-body" );
    Dom.clear( body );
    children.forEach( ( child ) => body.appendChild( child ) );
    const canvas = bootstrap.Offcanvas.getOrCreateInstance( Dom.get( "rr-editor" ) );
    if ( !this.editorWired ) {
      this.editorWired = true;
      Dom.get( "rr-editor" ).addEventListener( "hidden.bs.offcanvas" , () => this.drawBody() );
    }
    canvas.show();
    this.markProblems();
  },

  closeEditor() {
    bootstrap.Offcanvas.getOrCreateInstance( Dom.get( "rr-editor" ) ).hide();
  },

  labelled( label , control , help ) {
    const kids = [ Dom.el( "label" , { class: "form-label small mb-1" , text: label } ) , control ];
    if ( help ) kids.push( Dom.el( "div" , { class: "form-text" , text: help } ) );
    return Dom.el( "div" , { class: "mb-3" , children: kids } );
  },

  rangeInputs( holder , key , path ) {
    const span = holder[ key ] || [ "" , "" ];
    const set = ( i , value ) => {
      const next = ( holder[ key ] || [ "" , "" ] ).slice();
      next[ i ] = value === "" ? "" : Number( value );
      holder[ key ] = next[ 0 ] === "" && next[ 1 ] === "" ? null : next;
      this.edited();
    };
    const low = this.input( span[ 0 ] , ( value ) => set( 0 , value ) , { type: "number" , step: "any" , label: this.t( "range_min" ) } );
    const high = this.input( span[ 1 ] , ( value ) => set( 1 , value ) , { type: "number" , step: "any" , label: this.t( "range_max" ) , path: path } );
    return Dom.el( "div" , { class: "row g-2" , children: [
      Dom.el( "div" , { class: "col" , children: [ low ] } ),
      Dom.el( "div" , { class: "col" , children: [ high ] } ),
    ] } );
  },

  editField( index ) {
    const fields = this.draft.extraction.fields;
    const field = fields[ index ];
    const base = "extraction.fields[" + field.name + "]";
    const post = field.post;
    const name = this.input( field.name , ( value ) => { field.name = value; this.edited(); } , { path: base + ".name" , small: false } );
    const group = Dom.el( "select" , { class: "form-select" , children: this.snap.groups.map( ( g ) => Dom.el( "option" , { text: g , attrs: { value: g } } ) ) } );
    group.value = field.group;
    group.addEventListener( "change" , () => { field.group = group.value; this.edited(); } );
    const kind = Dom.el( "select" , { class: "form-select" , children: this.snap.post_kinds.map( ( k ) => Dom.el( "option" , { text: this.t( "kind_" + k ) , attrs: { value: k } } ) ) } );
    kind.value = post.kind;
    const postBox = Dom.el( "div" );
    const drawPost = () => {
      Dom.clear( postBox );
      if ( post.kind !== "seconds_or_ms" ) {
        postBox.appendChild( this.labelled( this.t( "post_template" ) , this.input( post.template || "" , ( value ) => { post.template = value; this.edited(); } , { mono: true , path: base + ".post.template" , small: false } ) , this.t( "post_template_help" ) ) );
      } else {
        postBox.appendChild( this.labelled( this.t( "post_ms_above" ) , this.input( post.ms_above == null ? 50 : post.ms_above , ( value ) => { post.ms_above = Number( value ); this.edited(); } , { type: "number" , step: "any" , small: false } ) ) );
      }
      if ( post.kind === "negation" ) {
        postBox.appendChild( this.labelled( this.t( "post_when" ) , this.input( post.when || "" , ( value ) => { post.when = value; this.edited(); } , { mono: true , path: base + ".post.when" , small: false } ) ) );
        postBox.appendChild( this.labelled( this.t( "post_value" ) , this.input( post.value || "" , ( value ) => { post.value = value; this.edited(); } , { small: false } ) ) );
      }
      const lower = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: "rr-post-lower" } } );
      lower.checked = !!post.lower;
      lower.addEventListener( "change" , () => { post.lower = lower.checked; this.edited(); } );
      postBox.appendChild( Dom.el( "div" , { class: "form-check mb-3" , children: [ lower , Dom.el( "label" , { class: "form-check-label" , text: this.t( "post_lower" ) , attrs: { for: "rr-post-lower" } } ) ] } ) );
      postBox.appendChild( this.labelled( this.t( "post_strip" ) , this.input( post.strip || "" , ( value ) => { post.strip = value; this.edited(); } , { mono: true , small: false } ) ) );
      postBox.appendChild( this.labelled( this.t( "post_replace" ) , this.input( Object.entries( post.replace || {} ).map( ( [ a , b ] ) => a + " = " + b ).join( "\n" ) , ( value ) => {
        const out = {};
        value.split( "\n" ).forEach( ( line ) => {
          const at = line.indexOf( "=" );
          if ( at > 0 ) out[ line.slice( 0 , at ).trim() ] = line.slice( at + 1 ).trim();
        } );
        post.replace = out;
        this.edited();
      } , { area: true , rows: 2 , mono: true } ) , this.t( "post_replace_help" ) ) );
    };
    kind.addEventListener( "change" , () => { post.kind = kind.value; this.edited(); drawPost(); } );
    drawPost();
    if ( !field.plausible ) field.plausible = null;
    const plausibleHolder = field.plausible || {};
    const ranges = Dom.el( "div" , { children: [
      this.labelled( this.t( "plausible_range" ) , this.rangeInputs( plausibleHolder , "range" , base + ".plausible.range" ) ),
      this.labelled( this.t( "plausible_seconds" ) , this.rangeInputs( plausibleHolder , "range_seconds" , base + ".plausible.range_seconds" ) ),
    ] } );
    // Ranges are kept on the field only when one is set.
    const syncPlausible = () => {
      const any = plausibleHolder.range || plausibleHolder.range_seconds;
      field.plausible = any ? { range: plausibleHolder.range || null , range_seconds: plausibleHolder.range_seconds || null } : null;
    };
    ranges.addEventListener( "input" , () => { syncPlausible(); this.edited(); } );
    const remove = Dom.el( "button" , {
      class: "btn btn-outline-danger btn-sm", attrs: { type: "button" }, text: this.t( "remove_field" ),
      on: { click: async () => {
        if ( !( await Dom.confirm( this.t( "remove_field_confirm" ) ) ) ) return;
        fields.splice( index , 1 );
        this.edited();
        this.closeEditor();
      } },
    } );
    const done = Dom.el( "button" , { class: "btn btn-primary btn-sm" , attrs: { type: "button" } , text: this.t( "done" ) , on: { click: () => this.closeEditor() } } );
    const mark = this.changedMark( () => field , [ "extraction" , "fields" , "@" + field.name ] , ( value ) => { fields[ index ] = value; this.closeEditor(); } );
    this.openEditor( this.t( "field_editor" ) + ": " + field.name , [
      Dom.el( "div" , { class: "mb-2" , children: [ mark ] } ),
      this.labelled( this.t( "field_name" ) , name ),
      this.labelled( this.t( "field_group" ) , group ),
      this.labelled( this.t( "col_patterns" ) , this.patterns( field.patterns , [ "extraction" , "fields" , "@" + field.name , "patterns" ] , base + ".patterns" ) , this.t( "vocab_help" ) ),
      this.labelled( this.t( "post_kind" ) , kind ),
      postBox,
      ranges,
      Dom.el( "div" , { class: "d-flex gap-2" , children: [ done , remove ] } ),
    ] );
  },

  drawDatasets( body ) {
    const cons = this.draft.consensus;
    body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "datasets_help" ) } ) );
    const numbers = {};
    Object.keys( cons ).forEach( ( key ) => {
      if ( cons[ key ] && typeof cons[ key ] === "object" && "value" in cons[ key ] ) numbers[ key ] = cons[ key ];
    } );
    const params = cons.params.map( ( param , i ) => {
      const input = this.input( param.pattern , ( value ) => { param.pattern = value; this.edited(); } , { mono: true , path: "consensus.params[" + param.name + "].pattern" , label: param.name } );
      const box = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , "aria-label": this.t( "ignore_case" ) } } );
      box.checked = param.ignore_case !== false;
      box.addEventListener( "change" , () => { param.ignore_case = box.checked; this.edited(); } );
      return Dom.el( "tr" , { children: [
        Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: param.name } ) ] } ),
        Dom.el( "td" , { children: [ input ] } ),
        Dom.el( "td" , { class: "text-center" , children: [ box ] } ),
      ] } );
    } );
    const ignore = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: "rr-aliases-case" } } );
    ignore.checked = !!cons.aliases_ignore_case;
    ignore.addEventListener( "change" , () => { cons.aliases_ignore_case = ignore.checked; this.edited(); } );
    const noise = this.input( cons.voxel_noise_left , ( value ) => { cons.voxel_noise_left = value; this.edited(); } , { mono: true , path: "consensus.voxel_noise_left" , label: this.t( "noise_left" ) } );
    const fallbackRows = Object.keys( cons.fallback ).map( ( field ) => {
      const select = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { "aria-label": field , "data-path": "consensus.fallback." + field } ,
        children: this.snap.params.map( ( p ) => Dom.el( "option" , { text: p , attrs: { value: p } } ) ) } );
      select.value = cons.fallback[ field ];
      select.addEventListener( "change" , () => { cons.fallback[ field ] = select.value; this.edited(); } );
      return Dom.el( "tr" , { children: [ Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: field } ) ] } ) , Dom.el( "td" , { children: [ select ] } ) ] } );
    } );
    body.appendChild( this.grid( [
      this.card( this.t( "consensus_heading" ) , "" , [] , [ this.thresholdTable( numbers , [ "consensus" ] , "consensus" ) ,
        Dom.el( "div" , { class: "form-check mt-2" , children: [ ignore , Dom.el( "label" , { class: "form-check-label small" , attrs: { for: "rr-aliases-case" } , text: this.t( "aliases_ignore_case" ) } ) ] } ) ] ),
      this.card( this.t( "params_heading" ) , "" , [] , [
        Dom.el( "div" , { class: "table-responsive" , children: [ Dom.el( "table" , { class: "table table-sm align-middle mb-2" , children: [
          Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: [
            Dom.el( "th" , { attrs: { scope: "col" } } ), Dom.el( "th" , { attrs: { scope: "col" } } ),
            Dom.el( "th" , { class: "small" , attrs: { scope: "col" } , text: this.t( "ignore_case" ) } ),
          ] } ) ] } ),
          Dom.el( "tbody" , { children: params } ),
        ] } ) ] } ),
        this.labelled( this.t( "noise_left" ) , noise ),
        Dom.el( "h5" , { class: "h6 small fw-semibold" , text: this.t( "fallback_heading" ) } ),
        Dom.el( "div" , { class: "table-responsive" , children: [ Dom.el( "table" , { class: "table table-sm align-middle mb-0" , children: [ Dom.el( "tbody" , { children: fallbackRows } ) ] } ) ] } ),
      ] ),
    ] , "row-cols-1" ) );
    const rows = this.draft.datasets.map( ( ds , i ) => {
      const changed = this.differs( ds , [ "datasets" , "@" + ds.name ] );
      return Dom.el( "tr" , { children: [
        Dom.el( "td" , { class: "small" , children: [ document.createTextNode( ds.name || "?" ) , changed ? Dom.el( "span" , { class: "badge text-bg-warning ms-2" , text: this.t( "changed" ) } ) : document.createTextNode( "" ) ] } ),
        Dom.el( "td" , { class: "small font-monospace text-break" , text: ds.aliases.join( "  ·  " ) } ),
        Dom.el( "td" , { class: "small text-break" , children: ds.home ? [ Dom.el( "a" , { text: ds.home.replace( /^https?:\/\// , "" ) , attrs: { href: ds.home , target: "_blank" , rel: "noopener" } } ) ] : [] } ),
        Dom.el( "td" , { class: "text-end" , children: [ Dom.el( "button" , {
          class: "btn btn-outline-secondary btn-sm", attrs: { type: "button" , "data-path": "datasets[" + ds.name + "]" },
          text: this.t( "edit" ), on: { click: () => this.editDataset( i ) },
        } ) ] } ),
      ] } );
    } );
    const head = Dom.el( "thead" , { children: [ Dom.el( "tr" , { children: [ "col_dataset" , "col_aliases" , "col_home" ].map( ( key ) =>
      Dom.el( "th" , { attrs: { scope: "col" } , text: this.t( key ) } ) ).concat( [ Dom.el( "th" , { attrs: { scope: "col" } } ) ] ) } ) ] } );
    body.appendChild( Dom.el( "div" , { class: "table-responsive mt-3" , children: [
      Dom.el( "table" , { class: "table table-sm table-hover align-middle mb-0" , children: [ head , Dom.el( "tbody" , { children: rows } ) ] } ),
    ] } ) );
    body.appendChild( Dom.el( "button" , {
      class: "btn btn-outline-primary btn-sm mt-3", attrs: { type: "button" },
      children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) , document.createTextNode( " " + this.t( "add_dataset" ) ) ],
      on: { click: () => {
        this.draft.datasets.push( { name: "New dataset" , aliases: [ "" ] , home: "" , description: "" } );
        this.edited();
        this.drawBody();
        this.editDataset( this.draft.datasets.length - 1 );
      } },
    } ) );
  },

  editDataset( index ) {
    const list = this.draft.datasets;
    const ds = list[ index ];
    const base = "datasets[" + ds.name + "]";
    const remove = Dom.el( "button" , {
      class: "btn btn-outline-danger btn-sm", attrs: { type: "button" }, text: this.t( "remove_dataset" ),
      on: { click: () => { list.splice( index , 1 ); this.edited(); this.closeEditor(); } },
    } );
    const done = Dom.el( "button" , { class: "btn btn-primary btn-sm" , attrs: { type: "button" } , text: this.t( "done" ) , on: { click: () => this.closeEditor() } } );
    this.openEditor( this.t( "dataset_editor" ) + ": " + ds.name , [
      this.labelled( this.t( "dataset_name" ) , this.input( ds.name , ( value ) => { ds.name = value; this.edited(); } , { path: base + ".name" , small: false } ) ),
      this.labelled( this.t( "dataset_aliases" ) , this.patterns( ds.aliases , [ "datasets" , "@" + ds.name , "aliases" ] , base + ".aliases" ) , this.t( "vocab_help" ) ),
      this.labelled( this.t( "dataset_home" ) , this.input( ds.home , ( value ) => { ds.home = value; this.edited(); } , { type: "url" , small: false } ) ),
      this.labelled( this.t( "dataset_description" ) , this.input( ds.description , ( value ) => { ds.description = value; this.edited(); } , { area: true , rows: 3 , small: false } ) ),
      Dom.el( "div" , { class: "d-flex gap-2" , children: [ done , remove ] } ),
    ] );
  },

  drawMissing( body ) {
    const missing = this.draft.missing;
    body.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "missing_help" ) } ) );
    const numbers = { precision: missing.precision , max_nearmiss: missing.max_nearmiss };
    const labels = Object.keys( missing.miss_labels ).map( ( key ) => {
      const input = this.input( missing.miss_labels[ key ] , ( value ) => { missing.miss_labels[ key ] = value; this.edited(); } , { path: "missing.miss_labels." + key , label: key } );
      return Dom.el( "tr" , { children: [ Dom.el( "td" , { children: [ Dom.el( "code" , { class: "small" , text: key } ) ] } ) , Dom.el( "td" , { children: [ input ] } ) ] } );
    } );
    const caveat = this.input( missing.caveat , ( value ) => { missing.caveat = value; this.edited(); } , { area: true , rows: 4 , path: "missing.caveat" , label: this.t( "caveat" ) } );
    body.appendChild( this.thresholdTable( numbers , [ "missing" ] , "missing" ) );
    body.appendChild( this.grid( [
      this.card( this.t( "miss_labels" ) , "" , [] , [ Dom.el( "div" , { class: "table-responsive" , children: [
        Dom.el( "table" , { class: "table table-sm align-middle mb-0" , children: [ Dom.el( "tbody" , { children: labels } ) ] } ) ] } ) ] ),
      this.card( this.t( "caveat" ) , "" , [] , [ caveat ] ),
    ] ) );
  },

  // ---- the test panel -----------------------------------------------------------------------

  async search() {
    const text = Dom.get( "rr-test-search" ).value.trim();
    const box = Dom.get( "rr-test-results" );
    const ticket = ++this.testTicket;
    if ( !text ) {
      Dom.clear( box );
      return;
    }
    let answer;
    try {
      answer = await Api.request( "/api/papers?" + new URLSearchParams( { q: text , limit: "8" , sort: "relevance" , dir: "desc" } ) );
    } catch ( error ) {
      return;
    }
    if ( ticket !== this.testTicket ) return;
    Dom.clear( box );
    if ( !answer.papers.length ) {
      box.appendChild( Dom.el( "div" , { class: "list-group-item text-body-secondary" , text: this.t( "test_none" ) } ) );
      return;
    }
    answer.papers.forEach( ( paper ) => box.appendChild( Dom.el( "button" , {
      class: "list-group-item list-group-item-action", attrs: { type: "button" },
      text: ( paper.title || paper.key ) + ( paper.year ? " (" + paper.year + ")" : "" ),
      on: { click: () => { this.pick( paper ); this.test(); } },
    } ) ) );
  },

  pick( paper ) {
    this.testKey = paper.key;
    const chosen = Dom.get( "rr-test-paper" );
    Dom.text( chosen , ( paper.title || paper.key ) + ( paper.year ? " (" + paper.year + ")" : "" ) );
    Dom.show( chosen , true );
    Dom.clear( Dom.get( "rr-test-results" ) );
    Dom.get( "rr-test-search" ).value = "";
  },

  async test() {
    const out = Dom.get( "rr-test-out" );
    const pasted = Dom.get( "rr-test-paste" ).checked;
    const body = { mode: Dom.get( "rr-test-mode" ).value };
    if ( this.dirty() ) body.rules = this.draft;
    else body.setup = this.setupId;
    if ( pasted ) {
      body.title = Dom.get( "rr-test-title" ).value;
      body.abstract = Dom.get( "rr-test-abstract" ).value;
      body.text = Dom.get( "rr-test-body" ).value;
    } else if ( this.testKey ) {
      body.key = this.testKey;
    } else {
      Dom.toast( this.t( "test_pick" ) , "error" );
      return;
    }
    Dom.clear( out );
    out.appendChild( Dom.el( "div" , { class: "spinner-border spinner-border-sm" , attrs: { role: "status" } } ) );
    let answer;
    try {
      answer = await Api.post( "/api/review/test" , body );
    } catch ( error ) {
      Dom.clear( out );
      if ( error.payload && error.payload.problems ) {
        this.problems = error.payload.problems;
        this.markProblems();
        this.drawHeader();
      }
      out.appendChild( Dom.el( "div" , { class: "alert alert-danger small" , text: error.message } ) );
      return;
    }
    Dom.clear( out );
    this.drawResult( out , answer );
  },

  verdictBadge( verdict ) {
    if ( verdict.include ) return Dom.el( "span" , { class: "badge text-bg-success" , text: this.t( "included" ) } );
    if ( verdict.borderline ) return Dom.el( "span" , { class: "badge text-bg-warning" , text: this.t( "borderline" ) } );
    return Dom.el( "span" , { class: "badge text-bg-danger" , text: this.t( "excluded" ) } );
  },

  verdictText( verdict ) {
    return verdict.include ? this.t( "included" ) : ( verdict.borderline ? this.t( "borderline" ) + ": " : this.t( "excluded" ) + ": " ) + ( verdict.reason || "" );
  },

  drawResult( out , answer ) {
    const result = answer.result;
    const verdict = result.verdict;
    const top = Dom.el( "div" , { class: "d-flex flex-wrap align-items-center gap-2 mb-1" , children: [ this.verdictBadge( verdict ) ] } );
    if ( !verdict.include && verdict.reason ) top.appendChild( Dom.el( "span" , { class: "small" , text: verdict.reason } ) );
    out.appendChild( top );
    out.appendChild( Dom.el( "div" , { class: "small text-body-secondary" , text: this.t( "task_line" , { task: verdict.task_category , n: verdict.priority } ) } ) );
    if ( verdict.near_miss ) out.appendChild( Dom.el( "div" , { class: "small" , text: this.t( "near_miss" , { what: verdict.near_miss } ) } ) );
    if ( result.model_name ) out.appendChild( Dom.el( "div" , { class: "small" , text: this.t( "model" , { name: result.model_name } ) } ) );
    if ( result.curated ) out.appendChild( Dom.el( "div" , { class: "small text-info-emphasis" , text: this.t( "curated" ) } ) );
    if ( answer.saved ) {
      const same = answer.saved.verdict.include === verdict.include && answer.saved.verdict.reason_code === verdict.reason_code;
      out.appendChild( Dom.el( "div" , { class: "alert alert-info small py-1 px-2 mt-2 mb-0" ,
        text: same ? this.t( "in_use_same" ) : this.t( "in_use_differs" , { verdict: this.verdictText( answer.saved.verdict ) } ) } ) );
    }
    out.appendChild( Dom.el( "h4" , { class: "h6 mt-3 mb-1" , text: this.t( "why_heading" ) } ) );
    out.appendChild( Dom.el( "ul" , { class: "list-group list-group-flush small" , children: ( verdict.why || [] ).map( ( test ) => {
      const kids = [
        Dom.el( "i" , { class: "bi me-1 " + ( test.pass ? "bi-check-circle-fill text-success" : "bi-x-circle-fill text-danger" ) , attrs: { "aria-hidden": "true" } } ),
        Dom.el( "span" , { class: "fw-semibold" , text: test.test } ),
        Dom.el( "div" , { class: "text-body-secondary" , text: test.detail } ),
      ];
      if ( test.terms && test.terms.length ) {
        kids.push( Dom.el( "div" , { class: "d-flex flex-wrap gap-1 mt-1" , children: test.terms.map( ( term ) => Dom.el( "span" , { class: "badge text-bg-light border fw-normal" , text: term } ) ) } ) );
      }
      return Dom.el( "li" , { class: "list-group-item px-0" , children: kids } );
    } ) } ) );
    if ( result.datasets && result.datasets.length ) {
      out.appendChild( Dom.el( "div" , { class: "small mt-2" , text: this.t( "datasets_named" , { names: result.datasets.join( ", " ) } ) } ) );
    }
    out.appendChild( Dom.el( "h4" , { class: "h6 mt-3 mb-1" , text: this.t( "fields_heading" ) } ) );
    const fields = Object.entries( result.fields || {} );
    const stated = fields.filter( ( [ , f ] ) => f.value );
    if ( !stated.length ) out.appendChild( Dom.el( "p" , { class: "small text-body-secondary" , text: this.t( "fields_none" ) } ) );
    this.snap.groups.forEach( ( group ) => {
      const rows = stated.filter( ( [ , f ] ) => f.group === group );
      if ( !rows.length ) return;
      out.appendChild( Dom.el( "div" , { class: "small fw-semibold mt-2" , text: group } ) );
      out.appendChild( Dom.el( "div" , { class: "table-responsive" , children: [ Dom.el( "table" , { class: "table table-sm small align-top mb-0" , children: [ Dom.el( "tbody" , {
        children: rows.map( ( [ name , f ] ) => this.fieldRow( name , f ) ),
      } ) ] } ) ] } ) );
    } );
    const missing = fields.length - stated.length;
    if ( missing ) out.appendChild( Dom.el( "div" , { class: "small text-body-secondary mt-2" , text: this.t( "not_stated" , { n: missing } ) } ) );
    const chars = ( answer.paper.body_chars || 0 ) + ( answer.paper.methods_chars || 0 ) + ( answer.paper.abstract_chars || 0 );
    out.appendChild( Dom.el( "div" , { class: "small text-body-secondary mt-2" , text: this.t( "test_took" , { ms: answer.elapsed_ms , chars: chars } ) } ) );
  },

  fieldRow( name , f ) {
    const value = Dom.el( "div" , { children: [ Dom.el( "span" , { text: f.value } ) ] } );
    if ( f.source === "curated" ) value.appendChild( Dom.el( "span" , { class: "badge text-bg-info ms-1" , text: this.t( "source_curated" ) } ) );
    if ( f.source === "dataset" ) value.appendChild( Dom.el( "span" , { class: "badge text-bg-secondary ms-1" , text: this.t( "source_dataset" , { dataset: f.from_dataset , n: f.dataset_papers } ) } ) );
    if ( f.values && f.values.length > 1 ) value.appendChild( Dom.el( "div" , { class: "text-body-secondary" , text: f.values.slice( 1 , 6 ).join( " · " ) } ) );
    if ( f.evidence && f.evidence.length ) {
      value.appendChild( Dom.el( "details" , { children: [
        Dom.el( "summary" , { class: "text-body-secondary" , text: this.t( "show_quote" ) } ),
        ...f.evidence.map( ( quote ) => Dom.el( "blockquote" , { class: "border-start ps-2 mb-1 text-body-secondary" , text: quote } ) ),
      ] } ) );
    }
    return Dom.el( "tr" , { children: [ Dom.el( "th" , { class: "fw-normal text-nowrap" , attrs: { scope: "row" } , children: [ Dom.el( "code" , { text: name } ) ] } ) , Dom.el( "td" , { children: [ value ] } ) ] } );
  },
};
