// The Code screen: one row per paper whose text links code -- the old /code
// page and `prma code`'s workbook.
//
// Each repository link carries what its host says about it (GitHub or OSF:
// description, stars, archived) and the methods it is about: ✓ confirmed in its
// README, · inferred from the papers that link it. A GitHub link the PDF text
// mangled ("…/Surfa", merged words) shows the repaired link with how sure the
// repair is. Lists, Tier and Figs say where the paper is curated.
//
// Every row is on the page, so sorting and filtering happen here, and the
// export is exactly what is shown, in that order (ExportTable).
const CodeView = {
  rows: [],
  hosts: new Set(),
  member: new Set(),
  loaded: false,

  init() {
    Dom.show( Dom.get( "code-panel" ) , true );
    Dom.typed( Dom.get( "code-search" ) , () => this.draw() , 200 );
    Dom.all( "[data-code-member]" ).forEach( ( box ) => box.addEventListener( "change" , () => {
      const name = box.getAttribute( "data-code-member" );
      if ( box.checked ) this.member.add( name );
      else this.member.delete( name );
      this.draw();
    } ) );
    this.table = new DataTable( {
      name: "code",
      holder: Dom.get( "code-table" ),
      menu: Dom.get( "code-columns" ),
      columns: this.columns(),
      sort: [ { col: "added" , desc: true } ],
    } );
    this.paintFilter = DataTable.filters( Dom.get( "code-filter" ) ,
      () => this.hosts.size + this.member.size,
      () => {
        this.hosts.clear();
        this.member.clear();
        Dom.all( "[data-code-member]" ).forEach( ( box ) => { box.checked = false; } );
        this.drawHosts();
        this.draw();
      } );
    Dom.onPress( Dom.get( "code-export-xlsx" ) , () => ExportTable.xlsx( "code" , [ this.sheetPapers() , this.sheetLinks() ] ) );
    Dom.onPress( Dom.get( "code-export-csv" ) , () => ExportTable.csv( "code" , this.sheetPapers() ) );
    const soon = Content.throttle( () => {
      if ( Nav.current() === "code" ) this.load();
      else this.stale = true;
    } , 30000 );
    Content.on( "enrich" , soon );
    Content.on( "paper" , ( data ) => { if ( data.stage === "code" || data.stage === "review" ) soon(); } );
    window.addEventListener( "hashchange" , () => {
      if ( Nav.current() === "code" && ( this.stale || !this.loaded ) ) this.load();
    } );
    if ( Nav.current() === "code" ) this.load();
  },

  async load() {
    this.stale = false;
    let answer;
    try {
      answer = await Api.request( "/api/code" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.loaded = true;
    this.rows = answer.papers;
    const notes = [];
    if ( !answer.enrich.github ) notes.push( I18n.get( "code.no_token" ) );
    if ( !answer.enrich.osf ) notes.push( I18n.get( "code.no_osf_token" ) );
    Dom.text( Dom.get( "code-note" ) , notes.join( " " ) );
    Dom.show( Dom.get( "code-note" ) , notes.length > 0 );
    this.drawHosts();
    this.draw();
  },

  drawHosts() {
    const holder = Dom.get( "code-hosts" );
    Dom.clear( holder );
    const counts = new Map();
    this.rows.forEach( ( row ) => new Set( row.code.map( ( link ) => link.host ) ).forEach( ( host ) => counts.set( host , ( counts.get( host ) || 0 ) + 1 ) ) );
    Array.from( counts.entries() ).sort( ( a , b ) => b[ 1 ] - a[ 1 ] ).forEach( ( [ host , n ] , index ) => {
      const id = "code-host-" + index;
      const box = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "checkbox" , id: id } } );
      box.checked = this.hosts.has( host );
      box.addEventListener( "change" , () => {
        if ( box.checked ) this.hosts.add( host );
        else this.hosts.delete( host );
        this.draw();
      } );
      holder.appendChild( Dom.el( "div" , { class: "form-check" , children: [ box , Dom.el( "label" , { class: "form-check-label" , attrs: { for: id } , text: host + " (" + n + ")" } ) ] } ) );
    } );
  },

  matches( row ) {
    if ( this.hosts.size && !row.code.some( ( link ) => this.hosts.has( link.host ) ) ) return false;
    if ( this.member.has( "list" ) && !row.lists.length ) return false;
    if ( this.member.has( "tier" ) && !row.tiers.length ) return false;
    if ( this.member.has( "figs" ) && !row.figs ) return false;
    if ( this.member.has( "review" ) && row.review !== "included" ) return false;
    const text = Dom.get( "code-search" ).value.trim().toLowerCase();
    if ( !text ) return true;
    const hay = [ row.title , row.doi , ( row.mods || [] ).join( " " ) , row.lists.map( ( l ) => l.name ).join( " " ) ,
      row.code.map( ( link ) => link.url + " " + ( ( link.info || {} ).description || "" ) ).join( " " ) ].join( " " ).toLowerCase();
    return text.split( /\s+/ ).every( ( word ) => hay.includes( word ) );
  },

  draw() {
    const shown = this.rows.filter( ( row ) => this.matches( row ) );
    this.table.rows( shown );
    this.paintFilter();
    Dom.text( Dom.get( "code-count" ) , I18n.get( "code.count" ).replace( "{n}" , shown.length.toLocaleString() ).replace( "{total}" , this.rows.length.toLocaleString() ) );
    Nav.summary( "code" , Dom.get( "code-count" ).textContent );
  },

  // -- the columns --------------------------------------------------------------

  columns() {
    return [
      { id: "title" , label: "code.col_paper" , sort: true , firstDesc: false , flex: true , lock: true , width: 18 ,
        value: ( row ) => ( row.title || "" ).toLowerCase() , cell: ( row ) => this.paperCell( row ) , text: ( row ) => row.title },
      { id: "year" , label: "table.col_year" , sort: true , align: "end" , width: 4.5 , value: ( row ) => row.year || null , cell: ( row ) => row.year || "" , text: ( row ) => row.year || "" },
      { id: "added" , label: "code.col_added" , sort: true , width: 7 , cellClass: "small text-nowrap" , value: ( row ) => row.added || "" ,
        cell: ( row ) => ( row.added || "" ).slice( 0 , 10 ) , text: ( row ) => ( row.added || "" ).slice( 0 , 10 ) },
      { id: "cites" , label: "code.col_cites" , sort: true , align: "end" , width: 5 , value: ( row ) => row.cites , cell: ( row ) => row.cites == null ? "" : row.cites.toLocaleString() , text: ( row ) => row.cites },
      { id: "links" , label: "code.col_links" , width: 24 , sort: true , value: ( row ) => Math.max( 0 , ...row.code.map( ( link ) => ( link.info || {} ).stars || 0 ) ) ,
        cell: ( row ) => this.linksCell( row ) , text: ( row ) => row.code.map( ( link ) => this.linkUrl( link ) ).join( "\n" ) },
      { id: "methods" , label: "code.col_methods" , width: 9 , sort: true , value: ( row ) => this.methods( row ).map( ( m ) => m.name ).join( " " ) ,
        cell: ( row ) => this.methodsCell( row ) , text: ( row ) => this.methods( row ).map( ( m ) => m.name + ( m.confirmed ? " ✓" : " ·" ) ).join( ", " ) },
      { id: "lists" , label: "code.col_list" , width: 10 , sort: true , value: ( row ) => row.lists.length || null , cell: ( row ) => this.listsCell( row.lists ) ,
        text: ( row ) => row.lists.map( ( l ) => l.name + " #" + l.position ).join( ", " ) },
      { id: "tier" , label: "code.col_tier" , width: 7 , sort: true , value: ( row ) => ( row.tiers[ 0 ] || {} ).tier || null , cell: ( row ) => this.tiersCell( row.tiers ) ,
        text: ( row ) => row.tiers.map( ( t ) => t.tier ).join( ", " ) },
      { id: "figs" , label: "code.col_figs" , sort: true , align: "end" , width: 4.5 , value: ( row ) => row.figs || null , cell: ( row ) => row.figs ? String( row.figs ) : "" , text: ( row ) => row.figs || "" },
      this.reviewColumn( "code.col_review" ),
      { id: "mods" , label: "table.col_modalities" , width: 9 , hide: true , sort: true , value: ( row ) => ( row.mods || [] ).join( " " ) ,
        cell: ( row ) => ( row.mods || [] ).join( ", " ) , text: ( row ) => ( row.mods || [] ).join( ", " ) },
      { id: "doi" , label: "table.col_doi" , width: 12 , hide: true , sort: true , cellClass: "small" , cell: ( row ) => row.doi || "" , text: ( row ) => row.doi || "" },
    ];
  },

  paperCell( row ) {
    const links = [];
    if ( row.doi ) links.push( PaperLinks.link( "https://doi.org/" + row.doi , "links.doi" , "links.doi_title" ) );
    if ( row.has_pdf ) links.push( PaperLinks.link( "/api/paper/pdf?key=" + encodeURIComponent( row.key ) , "links.pdf" , "links.pdf_title" ) );
    return Dom.el( "div" , { children: [ Dom.el( "div" , { children: [ Content.titleLink( row ) ] } ) , Dom.el( "div" , { class: "paper-links small mt-1" , children: links } ) ] } );
  },

  linkUrl( link ) {
    return link.repaired ? link.repaired.url : link.url;
  },

  linksCell( row ) {
    return Dom.el( "ul" , { class: "list-unstyled mb-0 small" , children: row.code.map( ( link ) => {
      const info = link.info || {};
      const url = this.linkUrl( link );
      const parts = [ Dom.el( "a" , { text: url.replace( /^https?:\/\// , "" ) , attrs: { href: url , target: "_blank" , rel: "noopener" } } ) ];
      const meta = [ link.host ];
      if ( info.stars ) meta.push( I18n.get( "code.stars" ).replace( "{n}" , info.stars.toLocaleString() ) );
      if ( info.language ) meta.push( info.language );
      if ( info.archived ) meta.push( I18n.get( "code.archived" ) );
      if ( info.status === "not_found" && !link.repaired ) meta.push( I18n.get( "code.not_found" ) );
      if ( info.status === "forbidden" ) meta.push( I18n.get( "code.forbidden" ) );
      parts.push( Dom.el( "span" , { class: "text-body-secondary" , text: " · " + meta.join( " · " ) } ) );
      if ( link.repaired ) {
        parts.push( Dom.el( "div" , { class: "text-warning-emphasis" , text: I18n.get( "code.repaired" )
          .replace( "{original}" , () => link.repaired.original || link.url ).replace( "{tier}" , link.repaired.tier || "" )
          .replace( "{confidence}" , Math.round( ( link.repaired.confidence || 0 ) * ( link.repaired.confidence <= 1 ? 100 : 1 ) ) ) } ) );
      }
      const about = info.description || info.title;
      if ( about ) parts.push( Dom.el( "div" , { class: "text-body-secondary code-about" , text: about , attrs: { title: about } } ) );
      return Dom.el( "li" , { class: "mb-1" , children: parts } );
    } ) } );
  },

  // Each method once: ✓ when a README confirms it, · when only inferred.
  methods( row ) {
    const out = new Map();
    row.code.forEach( ( link ) => {
      ( ( link.info || {} ).methods || [] ).forEach( ( name ) => out.set( name , true ) );
      ( link.inferred || [] ).forEach( ( name ) => { if ( !out.has( name ) ) out.set( name , false ); } );
    } );
    return Array.from( out.entries() ).map( ( [ name , confirmed ] ) => ( { name: name , confirmed: confirmed } ) );
  },

  methodsCell( row ) {
    return Dom.el( "span" , { class: "d-flex flex-wrap gap-1" , children: this.methods( row ).map( ( m ) => Dom.el( "span" , {
      class: "badge " + ( m.confirmed ? "bg-success-subtle text-success-emphasis border" : "text-bg-light border" ),
      text: m.name + ( m.confirmed ? " ✓" : " ·" ),
      attrs: { title: I18n.get( m.confirmed ? "code.confirmed_title" : "code.inferred_title" ) },
    } ) ) } );
  },

  // The Review column, shared with Datasets: the paper's verdict, linked to
  // the Review screen. Sorted included, borderline, excluded, waiting, then
  // papers that are no candidate.
  reviewColumn( label ) {
    const order = { included: 1 , borderline: 2 , excluded: 3 , waiting: 4 , failed: 5 };
    return { id: "review" , label: label , width: 7 , sort: true , value: ( row ) => order[ row.review ] || null ,
      cell: ( row ) => this.reviewCell( row.review ) , text: ( row ) => row.review ? I18n.get( "code.review_" + row.review ) : "" };
  },

  reviewCell( state ) {
    if ( !state ) return Dom.el( "span" , { class: "text-body-secondary" , text: "–" , attrs: { title: I18n.get( "code.review_none_title" ) } } );
    const tone = { included: "text-bg-success" , borderline: "text-bg-warning" , excluded: "text-bg-secondary" , failed: "text-bg-danger" }[ state ] || "text-bg-light border";
    return Dom.el( "a" , { class: "badge text-decoration-none " + tone , text: I18n.get( "code.review_" + state ) , attrs: { href: "#review" } } );
  },

  listsCell( lists ) {
    return Dom.el( "span" , { class: "small" , children: lists.map( ( list , index ) => Dom.el( "span" , { children: [
      index ? document.createTextNode( ", " ) : null,
      Dom.el( "a" , { text: list.name + " #" + list.position , attrs: { href: "#lists/" + encodeURIComponent( list.slug ) } } ),
    ].filter( Boolean ) } ) ) } );
  },

  tiersCell( tiers ) {
    return Dom.el( "span" , { class: "d-flex flex-wrap gap-1" , children: tiers.map( ( tier ) => {
      const badge = Dom.el( "span" , { class: "badge border text-body" , text: tier.tier , attrs: { title: tier.name } } );
      if ( tier.color ) badge.style.backgroundColor = tier.color + "33";
      return badge;
    } ) } );
  },

  // -- export ------------------------------------------------------------------

  sheetPapers() {
    return ExportTable.fromTable( this.table , I18n.get( "code.sheet_papers" ) );
  },

  // One row per link, in the papers' order.
  sheetLinks() {
    const rows = [];
    this.table.sorted( this.table.data ).forEach( ( row ) => row.code.forEach( ( link ) => {
      const info = link.info || {};
      rows.push( [ row.title , row.year || "" , row.doi || "" , this.linkUrl( link ) , link.host , info.description || info.title || "" ,
        info.stars == null ? "" : info.stars , ( info.methods || [] ).join( ", " ) , ( link.inferred || [] ).join( ", " ) ,
        link.repaired ? link.url : "" , link.where || "" ] );
    } ) );
    return { name: I18n.get( "code.sheet_links" ) , columns: [ "Paper" , "Year" , "DOI" , "Link" , "Host" , "Description" , "Stars" , "Methods (README)" , "Methods (inferred)" , "Printed as" , "Found in" ] , rows: rows };
  },
};

// The Code and Datasets screens' exports: what the table shows, as it shows
// it (its shown columns in their order, its rows in their sort and filter).
const ExportTable = {
  fromTable( table , name ) {
    const columns = table.visible();
    return {
      name: name,
      columns: columns.map( ( column ) => I18n.get( column.label ) ),
      rows: table.sorted( table.data ).map( ( row ) => columns.map( ( column ) => {
        const value = column.text ? column.text( row ) : row[ column.id ];
        return value == null ? "" : value;
      } ) ),
    };
  },

  async xlsx( name , sheets ) {
    try {
      await Api.download( "/api/export/xlsx" , { filename: name , sheets: sheets } , name + ".xlsx" );
    } catch ( error ) {
      Dom.toast( error.message , "error" );
    }
  },

  csv( name , sheet ) {
    const quote = ( value ) => {
      const text = String( value == null ? "" : value );
      return /[",\n\r]/.test( text ) ? '"' + text.replace( /"/g , '""' ) + '"' : text;
    };
    const lines = [ sheet.columns.map( quote ).join( "," ) ].concat( sheet.rows.map( ( row ) => row.map( quote ).join( "," ) ) );
    Dom.download( name + ".csv" , lines.join( "\r\n" ) + "\r\n" );
  },
};
