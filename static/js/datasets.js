// The Datasets screen: what public data the library stands on -- the old
// /datasets page. Two views of the same rows (GET /api/datasets):
//
//   By dataset  one row per archive record or named collection: what it is
//               (the archive's own words, or a written line for a named
//               collection), how many papers use it, how many of those are on
//               lists or in tiers, the years; it opens to the full roll call.
//   By paper    one row per paper: the records it links (what it printed; a
//               record recovered from a bare ds###### is marked ˟), the
//               collections it names, its code (linking to the Code screen).
//
// Every row is on the page, so sorting, filtering and the export are done
// here: the export is exactly what is shown (ExportTable, in code.js).
const DatasetsView = {
  view: "datasets",
  papers: [],
  kinds: new Set(),
  member: new Set(),
  archive: "",
  loaded: false,

  init() {
    Dom.show( Dom.get( "datasets-panel" ) , true );
    Dom.all( "[data-datasets-view]" ).forEach( ( tab ) => tab.addEventListener( "click" , ( event ) => {
      event.preventDefault();
      this.setView( tab.getAttribute( "data-datasets-view" ) );
    } ) );
    Dom.typed( Dom.get( "datasets-search" ) , () => this.draw() , 200 );
    Dom.all( "[data-datasets-kind]" ).forEach( ( box ) => box.addEventListener( "change" , () => {
      this.toggle( this.kinds , box.getAttribute( "data-datasets-kind" ) , box.checked );
    } ) );
    Dom.all( "[data-datasets-member]" ).forEach( ( box ) => box.addEventListener( "change" , () => {
      this.toggle( this.member , box.getAttribute( "data-datasets-member" ) , box.checked );
    } ) );
    Dom.get( "datasets-archive" ).addEventListener( "change" , ( event ) => { this.archive = event.target.value; this.draw(); } );
    this.byDataset = new DataTable( {
      name: "datasets",
      holder: Dom.get( "datasets-table" ),
      menu: Dom.get( "datasets-columns" ),
      columns: this.datasetColumns(),
      sort: [ { col: "papers" , desc: true } ],
    } );
    this.byPaperHolder = Dom.el( "div" , { class: "table-fill" , attrs: { hidden: "" } } );
    Dom.get( "datasets-table" ).after( this.byPaperHolder );
    // Each table fills its own Columns list; the one showing is the menu.
    this.byPaperMenu = Dom.el( "ul" , { class: "dropdown-menu data-table-menu" , attrs: { hidden: "" } } );
    Dom.get( "datasets-columns" ).after( this.byPaperMenu );
    this.byPaper = new DataTable( {
      name: "datasets-papers",
      holder: this.byPaperHolder,
      menu: this.byPaperMenu,
      columns: this.paperColumns(),
      sort: [ { col: "added" , desc: true } ],
    } );
    this.paintFilter = DataTable.filters( Dom.get( "datasets-filter" ) ,
      () => this.kinds.size + this.member.size + ( this.archive ? 1 : 0 ),
      () => {
        this.kinds.clear();
        this.member.clear();
        this.archive = "";
        Dom.all( "[data-datasets-kind], [data-datasets-member]" ).forEach( ( box ) => { box.checked = false; } );
        this.draw();
      } );
    Dom.onPress( Dom.get( "datasets-export-xlsx" ) , () => this.exportXlsx() );
    Dom.onPress( Dom.get( "datasets-export-csv" ) , () => ExportTable.csv( "datasets-" + this.view , ExportTable.fromTable( this.table() , this.sheetName() ) ) );
    const soon = Content.throttle( () => {
      if ( Nav.current() === "datasets" ) this.load();
      else this.stale = true;
    } , 30000 );
    Content.on( "enrich" , soon );
    Content.on( "paper" , ( data ) => { if ( data.stage === "datasets" || data.stage === "review" ) soon(); } );
    window.addEventListener( "hashchange" , () => {
      if ( Nav.current() === "datasets" && ( this.stale || !this.loaded ) ) this.load();
    } );
    if ( Nav.current() === "datasets" ) this.load();
  },

  toggle( set , name , on ) {
    if ( on ) set.add( name );
    else set.delete( name );
    this.draw();
  },

  table() {
    return this.view === "datasets" ? this.byDataset : this.byPaper;
  },

  sheetName() {
    return I18n.get( this.view === "datasets" ? "datasets.sheet_datasets" : "datasets.sheet_papers" );
  },

  setView( view ) {
    this.view = view;
    Dom.all( "[data-datasets-view]" ).forEach( ( tab ) => {
      const on = tab.getAttribute( "data-datasets-view" ) === view;
      tab.classList.toggle( "active" , on );
      if ( on ) tab.setAttribute( "aria-current" , "true" );
      else tab.removeAttribute( "aria-current" );
    } );
    Dom.show( Dom.get( "datasets-table" ) , view === "datasets" );
    Dom.show( this.byPaperHolder , view === "papers" );
    // Each table has its own Columns list in the same dropdown.
    Dom.show( Dom.get( "datasets-columns" ) , view === "datasets" );
    Dom.show( this.byPaperMenu , view === "papers" );
    this.draw();
  },

  async load() {
    this.stale = false;
    let answer;
    try {
      answer = await Api.request( "/api/datasets" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.loaded = true;
    this.papers = answer.papers;
    this.drawArchives();
    this.draw();
  },

  drawArchives() {
    const select = Dom.get( "datasets-archive" );
    const counts = new Map();
    this.papers.forEach( ( paper ) => new Set( paper.data.map( ( link ) => link.host ) ).forEach( ( host ) => counts.set( host , ( counts.get( host ) || 0 ) + 1 ) ) );
    Dom.clear( select );
    select.appendChild( Dom.el( "option" , { text: I18n.get( "figures.any" ) , attrs: { value: "" } } ) );
    Array.from( counts.entries() ).sort( ( a , b ) => b[ 1 ] - a[ 1 ] ).forEach( ( [ host , n ] ) => {
      select.appendChild( Dom.el( "option" , { text: host + " (" + n + ")" , attrs: { value: host } } ) );
    } );
    select.value = this.archive;
  },

  // -- the two views' rows -----------------------------------------------------

  paperMatches( paper ) {
    if ( this.kinds.has( "linked" ) && !paper.data.length ) return false;
    if ( this.kinds.has( "named" ) && !( paper.names.length && !paper.data.length ) ) return false;
    if ( this.member.has( "code" ) && !paper.code_n ) return false;
    if ( this.member.has( "list" ) && !paper.lists.length ) return false;
    if ( this.member.has( "tier" ) && !paper.tiers.length ) return false;
    if ( this.member.has( "review" ) && paper.review !== "included" ) return false;
    if ( this.archive && !paper.data.some( ( link ) => link.host === this.archive ) ) return false;
    return true;
  },

  searched( text , hay ) {
    if ( !text ) return true;
    const lower = hay.toLowerCase();
    return text.split( /\s+/ ).every( ( word ) => lower.includes( word ) );
  },

  // Every dataset, with its papers: archive records by their record, named
  // collections by name.
  datasets( papers ) {
    const out = new Map();
    const add = ( id , make , paper ) => {
      if ( !out.has( id ) ) out.set( id , Object.assign( make() , { papers: [] } ) );
      const entry = out.get( id );
      if ( !entry.papers.includes( paper ) ) entry.papers.push( paper );
    };
    papers.forEach( ( paper ) => {
      paper.data.forEach( ( link ) => {
        if ( this.archive && link.host !== this.archive ) return;
        const info = link.info || {};
        add( link.target || link.url , () => ( {
          name: info.title || link.url.replace( /^https?:\/\// , "" ), url: link.url, host: link.host, description: info.description || "",
          status: info.status || "", named: false,
        } ) , paper );
      } );
      if ( !this.archive && !this.kinds.has( "linked" ) ) {
        paper.names.forEach( ( name ) => add( "name:" + name.name , () => ( {
          name: name.name, url: name.url || "", host: I18n.get( "datasets.named" ), description: name.description || "", named: true,
        } ) , paper ) );
      }
    } );
    return Array.from( out.values() ).map( ( entry ) => {
      const years = entry.papers.map( ( p ) => p.year ).filter( Boolean );
      entry.lists = entry.papers.filter( ( p ) => p.lists.length ).length;
      entry.tiers = entry.papers.filter( ( p ) => p.tiers.length ).length;
      entry.from = years.length ? Math.min( ...years ) : null;
      entry.to = years.length ? Math.max( ...years ) : null;
      return entry;
    } );
  },

  draw() {
    if ( !this.loaded ) return;
    const text = Dom.get( "datasets-search" ).value.trim().toLowerCase();
    const papers = this.papers.filter( ( paper ) => this.paperMatches( paper ) );
    let shown;
    let total;
    if ( this.view === "datasets" ) {
      const all = this.datasets( papers );
      shown = all.filter( ( entry ) => this.searched( text , [ entry.name , entry.description , entry.host , entry.url ,
        entry.papers.map( ( p ) => p.title + " " + p.doi ).join( " " ) ].join( " " ) ) );
      total = this.datasets( this.papers ).length;
      this.byDataset.rows( shown );
    } else {
      shown = papers.filter( ( paper ) => this.searched( text , [ paper.title , paper.doi ,
        paper.data.map( ( link ) => link.url + " " + ( ( link.info || {} ).title || "" ) ).join( " " ) , paper.names.map( ( n ) => n.name ).join( " " ) ].join( " " ) ) );
      total = this.papers.length;
      this.byPaper.rows( shown );
    }
    this.paintFilter();
    Dom.text( Dom.get( "datasets-count" ) , I18n.get( "datasets.count" ).replace( "{n}" , shown.length.toLocaleString() ).replace( "{total}" , total.toLocaleString() ) );
    Nav.summary( "datasets" , Dom.get( "datasets-count" ).textContent );
  },

  // -- columns -------------------------------------------------------------------

  datasetColumns() {
    return [
      { id: "name" , label: "datasets.col_dataset" , sort: true , firstDesc: false , flex: true , lock: true , width: 16 ,
        value: ( row ) => row.name.toLowerCase() , cell: ( row ) => this.datasetCell( row ) , text: ( row ) => row.name },
      { id: "description" , label: "datasets.col_description" , width: 22 , cellClass: "small" , cell: ( row ) => row.description , text: ( row ) => row.description },
      { id: "host" , label: "datasets.archive_label" , sort: true , width: 8 , cellClass: "small" , cell: ( row ) => row.host , text: ( row ) => row.host },
      { id: "papers" , label: "datasets.col_papers" , sort: true , width: 14 , value: ( row ) => row.papers.length ,
        cell: ( row ) => this.rollCall( row ) , text: ( row ) => row.papers.length },
      { id: "lists" , label: "datasets.col_lists" , sort: true , align: "end" , width: 5 , value: ( row ) => row.lists || null , cell: ( row ) => row.lists ? String( row.lists ) : "" , text: ( row ) => row.lists },
      { id: "tiers" , label: "datasets.col_tiers" , sort: true , align: "end" , width: 5 , value: ( row ) => row.tiers || null , cell: ( row ) => row.tiers ? String( row.tiers ) : "" , text: ( row ) => row.tiers },
      { id: "years" , label: "datasets.col_years" , sort: true , width: 7 , value: ( row ) => row.to , cell: ( row ) => this.years( row ) , text: ( row ) => this.years( row ) },
      { id: "url" , label: "table.col_links" , width: 14 , hide: true , cellClass: "small" , cell: ( row ) => row.url , text: ( row ) => row.url },
    ];
  },

  years( row ) {
    if ( !row.from ) return "";
    return row.from === row.to ? String( row.from ) : row.from + "–" + row.to;
  },

  datasetCell( row ) {
    const name = row.url ? Dom.el( "a" , { text: row.name , attrs: { href: row.url , target: "_blank" , rel: "noopener" } } ) : Dom.el( "span" , { text: row.name } );
    return Dom.el( "div" , { children: [ name , row.named ? Dom.el( "span" , { class: "badge text-bg-light border ms-1" , text: I18n.get( "datasets.named" ) } ) : null ].filter( Boolean ) } );
  },

  // The papers that use a dataset, folded until asked for.
  rollCall( row ) {
    const list = Dom.el( "ul" , { class: "list-unstyled small mb-0 mt-1" , children: row.papers
      .slice().sort( ( a , b ) => ( b.year || 0 ) - ( a.year || 0 ) )
      .map( ( paper ) => Dom.el( "li" , { children: [ Content.titleLink( paper ) , Dom.el( "span" , { class: "text-body-secondary" , text: paper.year ? " · " + paper.year : "" } ) ] } ) ) } );
    return Dom.el( "details" , { children: [ Dom.el( "summary" , { text: I18n.get( "datasets.roll_call" ).replace( "{n}" , row.papers.length ) } ) , list ] } );
  },

  paperColumns() {
    return [
      { id: "title" , label: "datasets.col_paper" , sort: true , firstDesc: false , flex: true , lock: true , width: 18 ,
        value: ( row ) => ( row.title || "" ).toLowerCase() , cell: ( row ) => CodeView.paperCell( row ) , text: ( row ) => row.title },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 4.5 , value: ( row ) => row.year || null , cell: ( row ) => row.year || "" , text: ( row ) => row.year || "" },
      { id: "added" , label: "datasets.col_added" , sort: true , width: 7 , cellClass: "small text-nowrap" , value: ( row ) => row.added || "" ,
        cell: ( row ) => ( row.added || "" ).slice( 0 , 10 ) , text: ( row ) => ( row.added || "" ).slice( 0 , 10 ) },
      { id: "data" , label: "datasets.col_data" , width: 24 , sort: true , value: ( row ) => row.data.length + row.names.length ,
        cell: ( row ) => this.dataCell( row ) , text: ( row ) => row.data.map( ( link ) => link.url ).concat( row.names.map( ( n ) => n.name ) ).join( "\n" ) },
      { id: "code" , label: "datasets.col_code" , sort: true , align: "end" , width: 5 , value: ( row ) => row.code_n || null ,
        cell: ( row ) => row.code_n ? Dom.el( "a" , { text: String( row.code_n ) , attrs: { href: "#code" , title: I18n.get( "datasets.code_link_title" ) } , on: { click: () => this.showCode( row ) } } ) : "" ,
        text: ( row ) => row.code_n || "" },
      { id: "lists" , label: "datasets.col_list" , width: 10 , sort: true , value: ( row ) => row.lists.length || null , cell: ( row ) => CodeView.listsCell( row.lists ) ,
        text: ( row ) => row.lists.map( ( l ) => l.name + " #" + l.position ).join( ", " ) },
      { id: "tier" , label: "datasets.col_tier" , width: 7 , sort: true , value: ( row ) => ( row.tiers[ 0 ] || {} ).tier || null , cell: ( row ) => CodeView.tiersCell( row.tiers ) ,
        text: ( row ) => row.tiers.map( ( t ) => t.tier ).join( ", " ) },
      { id: "figs" , label: "datasets.col_figs" , sort: true , align: "end" , width: 4.5 , value: ( row ) => row.figs || null , cell: ( row ) => row.figs ? String( row.figs ) : "" , text: ( row ) => row.figs || "" },
      CodeView.reviewColumn( "datasets.col_review" ),
      { id: "doi" , label: "table.col_doi" , width: 12 , hide: true , sort: true , cellClass: "small" , cell: ( row ) => row.doi || "" , text: ( row ) => row.doi || "" },
    ];
  },

  showCode( row ) {
    Dom.get( "code-search" ).value = row.doi || row.title || "";
    if ( CodeView.loaded ) CodeView.draw();
  },

  dataCell( row ) {
    const items = row.data.map( ( link ) => {
      const info = link.info || {};
      const label = info.title || link.url.replace( /^https?:\/\// , "" );
      return Dom.el( "li" , { children: [
        Dom.el( "a" , { text: label , attrs: { href: link.url , target: "_blank" , rel: "noopener" , title: link.url } } ),
        link.accession ? Dom.el( "span" , { class: "ms-1 text-warning-emphasis" , text: I18n.get( "datasets.recovered" ) , attrs: { title: I18n.get( "datasets.recovered_title" ) } } ) : null,
        Dom.el( "span" , { class: "text-body-secondary" , text: " · " + link.host } ),
      ].filter( Boolean ) } );
    } );
    row.names.forEach( ( name ) => items.push( Dom.el( "li" , { children: [
      name.url ? Dom.el( "a" , { text: name.name , attrs: { href: name.url , target: "_blank" , rel: "noopener" } } ) : Dom.el( "span" , { text: name.name } ),
      Dom.el( "span" , { class: "text-body-secondary" , text: " · " + I18n.get( "datasets.named" ) } ),
    ] } ) ) );
    return Dom.el( "ul" , { class: "list-unstyled small mb-0" , children: items } );
  },

  // -- export ------------------------------------------------------------------

  exportXlsx() {
    const sheets = [ ExportTable.fromTable( this.table() , this.sheetName() ) ];
    if ( this.view === "papers" ) {
      // And one row per paper and dataset, for a pivot.
      const rows = [];
      this.byPaper.sorted( this.byPaper.data ).forEach( ( paper ) => {
        paper.data.forEach( ( link ) => rows.push( [ paper.title , paper.year || "" , paper.doi || "" , ( link.info || {} ).title || "" , link.url , link.host ,
          link.accession ? "recovered" : "printed" , ( link.info || {} ).description || "" ] ) );
        paper.names.forEach( ( name ) => rows.push( [ paper.title , paper.year || "" , paper.doi || "" , name.name , name.url || "" , "named" , "named" , name.description || "" ] ) );
      } );
      sheets.push( { name: I18n.get( "datasets.sheet_pairs" ) , columns: [ "Paper" , "Year" , "DOI" , "Dataset" , "Link" , "Archive" , "Evidence" , "Description" ] , rows: rows } );
    }
    ExportTable.xlsx( "datasets-" + this.view , sheets );
  },
};
