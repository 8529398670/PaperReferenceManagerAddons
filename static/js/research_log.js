// The Research log screen: which papers in a Markdown research log are not in
// the library (the old `prma check-missing-file`). Paste the log or pick the
// .md; the server lifts each paper's title and DOI out of it and checks each
// the way the userscripts' /exists does (app/extras/logcheck.py).
//
// Missing papers can go onto a list, or be looked up on the Missing screen;
// "Found by title only" are those whose DOI in the log is not the library's
// (usually a preprint DOI for a journal version). "List only" shows what the
// parser read, for a log whose layout drifted.
const ResearchLog = {
  answer: null,
  tab: "missing",
  name: "research log",

  init() {
    Dom.show( Dom.get( "research-log-panel" ) , true );
    Dom.get( "log-file" ).addEventListener( "change" , () => this.readFile() );
    Dom.onSubmit( Dom.get( "log-form" ) , ( event ) => {
      event.preventDefault();
      return this.check();
    } );
    Dom.onPress( Dom.get( "log-download" ) , () => {
      if ( this.answer && this.answer.report ) Dom.download( this.name.replace( /\.[^.]+$/ , "" ) + "-missing.md" , this.answer.report );
    } );
    Dom.all( "[data-log-tab]" ).forEach( ( tab ) => tab.addEventListener( "click" , ( event ) => {
      event.preventDefault();
      this.tab = tab.getAttribute( "data-log-tab" );
      this.draw();
    } ) );
    // Dropping a file anywhere on the form reads it.
    const form = Dom.get( "log-form" );
    form.addEventListener( "dragover" , ( event ) => event.preventDefault() );
    form.addEventListener( "drop" , ( event ) => {
      event.preventDefault();
      const file = event.dataTransfer && event.dataTransfer.files[ 0 ];
      if ( file ) this.readFile( file );
    } );
    this.table = new DataTable( {
      name: "research-log",
      holder: Dom.get( "log-results" ),
      menu: null,
      columns: this.columns(),
      sort: [ { col: "line" , desc: false } ],
    } );
  },

  async readFile( given ) {
    const file = given || Dom.get( "log-file" ).files[ 0 ];
    if ( !file ) return;
    this.name = file.name;
    Dom.get( "log-text" ).value = await file.text();
  },

  async check() {
    const text = Dom.get( "log-text" ).value;
    if ( !text.trim() ) {
      Dom.toast( I18n.get( "research_log.nothing" ) , "error" );
      return;
    }
    try {
      this.answer = await Api.post( "/api/research-log/check" , { text: text , name: this.name , list_only: Dom.get( "log-list-only" ).checked } );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    const listOnly = this.answer.report === "";
    this.tab = listOnly ? "all" : "missing";
    const a = this.answer;
    Dom.text( Dom.get( "log-summary" ) , ( listOnly ? I18n.get( "research_log.summary_list" ) : I18n.get( "research_log.summary" ) )
      .replace( "{extracted}" , a.extracted.toLocaleString() ).replace( "{unique}" , a.unique.toLocaleString() )
      .replace( "{lines}" , a.lines.toLocaleString() ).replace( "{missing}" , ( a.missing || 0 ).toLocaleString() )
      .replace( "{recovered}" , ( a.recovered || 0 ).toLocaleString() ) );
    Dom.show( Dom.get( "log-download" ) , !listOnly );
    Dom.show( Dom.get( "log-results-card" ) , true );
    Nav.summary( "research-log" , Dom.get( "log-summary" ).textContent );
    this.draw();
  },

  shown() {
    const papers = ( this.answer && this.answer.papers ) || [];
    if ( this.tab === "missing" ) return papers.filter( ( p ) => p.found === "" );
    if ( this.tab === "recovered" ) return papers.filter( ( p ) => p.recovered );
    return papers;
  },

  draw() {
    const papers = ( this.answer && this.answer.papers ) || [];
    const listOnly = this.answer && this.answer.report === "";
    const counts = { missing: papers.filter( ( p ) => p.found === "" ).length , recovered: papers.filter( ( p ) => p.recovered ).length , all: papers.length };
    Dom.all( "[data-log-tab]" ).forEach( ( tab ) => {
      const name = tab.getAttribute( "data-log-tab" );
      Dom.show( tab.parentElement , !listOnly || name === "all" );
      tab.classList.toggle( "active" , name === this.tab );
      if ( name === this.tab ) tab.setAttribute( "aria-current" , "page" );
      else tab.removeAttribute( "aria-current" );
      Dom.text( tab.querySelector( ".badge" ) , counts[ name ].toLocaleString() );
    } );
    this.table.redraw();
    this.table.rows( this.shown() );
  },

  columns() {
    const checked = () => this.answer && this.answer.report !== "";
    return [
      { id: "line" , label: "research_log.col_line" , sort: true , firstDesc: false , align: "end" , width: 5 , cellClass: "text-body-secondary" },
      { id: "date" , label: "research_log.col_date" , sort: true , width: 7 , cellClass: "small" , value: ( p ) => this.dateValue( p.date ) , cell: ( p ) => p.date || "" },
      { id: "title" , label: "table.col_title" , sort: true , firstDesc: false , flex: true , lock: true , width: 22 , cell: ( p ) => (
        p.key
          ? Dom.el( "a" , { class: "paper-title" , text: p.title , attrs: { href: "#paper/" + encodeURIComponent( p.key ) } } )
          : Dom.el( "span" , { class: "paper-title" , text: p.title } )
      ) },
      { id: "doi" , label: "research_log.col_doi" , sort: true , width: 12 , cellClass: "small text-break" , cell: ( p ) => (
        p.doi ? Dom.el( "a" , { text: p.doi , attrs: { href: "https://doi.org/" + p.doi , target: "_blank" , rel: "noopener" } } ) : ""
      ) },
      { id: "url" , label: "research_log.col_link" , width: 6 , cell: ( p ) => (
        p.url ? Dom.el( "a" , { text: I18n.get( "research_log.source" ) , attrs: { href: p.url , target: "_blank" , rel: "noopener noreferrer" } } ) : ""
      ) },
      { id: "mentions" , label: "research_log.col_mentions" , title: "research_log.col_mentions_title" , sort: true , align: "end" , width: 6 },
      { id: "found" , label: "research_log.col_found" , width: 8 , when: checked , cell: ( p ) => {
        if ( p.recovered ) return Dom.badge( I18n.get( "research_log.found_recovered" ) , "warning" );
        if ( p.found ) return Dom.badge( I18n.get( "research_log.found_" + p.found ) , "success" );
        return Dom.badge( I18n.get( "research_log.found_none" ) , "danger" );
      } },
      { id: "actions" , label: "table.col_actions" , align: "end" , width: 9 , when: checked , cell: ( p ) => {
        if ( p.found ) return "";
        const add = Dom.el( "button" , {
          class: "btn btn-outline-primary btn-sm",
          attrs: { type: "button" , title: I18n.get( "missing.add_title" ) , "aria-label": I18n.get( "missing.add_title" ) },
          children: [ Dom.el( "i" , { class: "bi bi-plus-lg" , attrs: { "aria-hidden": "true" } } ) ],
          on: { click: () => Missing.addToList( { title: p.title , doi: p.doi } ) },
        } );
        const look = Dom.el( "a" , {
          class: "btn btn-outline-secondary btn-sm",
          attrs: { href: "#missing" , title: I18n.get( "research_log.open_missing" ) , "aria-label": I18n.get( "research_log.open_missing" ) },
          children: [ Dom.el( "i" , { class: "bi bi-search-heart" , attrs: { "aria-hidden": "true" } } ) ],
          on: { click: () => { Dom.get( "missing-search" ).value = p.doi || '"' + p.title + '"'; Missing.tab = "all"; Missing.dirty = true; } },
        } );
        return Dom.el( "div" , { class: "d-inline-flex gap-1" , children: [ add , look ] } );
      } },
    ];
  },

  // "03SEP2026" sorts as 2026-09-03.
  dateValue( text ) {
    const months = [ "JAN" , "FEB" , "MAR" , "APR" , "MAY" , "JUN" , "JUL" , "AUG" , "SEP" , "OCT" , "NOV" , "DEC" ];
    const match = /^(\d{1,2})([A-Z]{3})(\d{4})$/.exec( text || "" );
    if ( !match ) return "";
    return match[ 3 ] + "-" + String( months.indexOf( match[ 2 ] ) + 1 ).padStart( 2 , "0" ) + "-" + match[ 1 ].padStart( 2 , "0" );
  },
};
