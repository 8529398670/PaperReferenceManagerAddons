// The links every paper carries, built in one place so every screen shows
// the same ones the same way: DOI (the publisher), Proxy (the same DOI
// through the library proxy, when config.yaml's library.proxy_url is set) and
// PDF (the file in Zotero, served by the app).
//
// Also the bits of a paper's row every screen shares: its author line, and
// the pastel colour a tag is drawn in.
const PaperLinks = {
  proxyUrl: "",
  loaded: null,

  init() {
    if ( !this.loaded ) {
      this.loaded = Api.request( "/api/library/links" ).then( ( links ) => {
        this.proxyUrl = links.proxy_url || "";
      } ).catch( () => {} );
    }
    return this.loaded;
  },

  link( href , labelKey , titleKey ) {
    return Dom.el( "a" , {
      class: "paper-link",
      text: I18n.get( labelKey ),
      attrs: { href: href , target: "_blank" , rel: "noopener" , title: I18n.get( titleKey ) },
    } );
  },

  // paper needs key, doi, and has_pdf.
  strip( paper ) {
    const links = [];
    if ( paper.doi ) {
      links.push( this.link( "https://doi.org/" + paper.doi , "links.doi" , "links.doi_title" ) );
      if ( this.proxyUrl ) {
        links.push( this.link( this.proxyUrl.replace( "{doi}" , () => paper.doi ) , "links.proxy" , "links.proxy_title" ) );
      }
    }
    if ( paper.has_pdf ) {
      links.push( this.link( "/api/paper/pdf?key=" + encodeURIComponent( paper.key ) , "links.pdf" , "links.pdf_title" ) );
    }
    return Dom.el( "span" , { class: "paper-links" , children: links } );
  },

  // "A. Smith, B. Jones, C. Wu et al."
  authors( names , total ) {
    const list = ( names || [] ).slice( 0 , 3 );
    const count = total == null ? ( names || [] ).length : total;
    let text = list.join( ", " );
    if ( count > list.length ) text += " " + I18n.get( "library.et_al" );
    return text;
  },

  // The meta line under a title: authors · year · journal.
  meta( paper , total ) {
    return [ this.authors( paper.authors , total ) , paper.year || "" , paper.journal || "" ].filter( Boolean ).join( " · " );
  },
};

// Tag colours: a pastel per tag, so a row's tags read as a pattern. A tag
// with a stored colour (the list's vocabulary) uses it; one without falls back
// to a colour picked from its name, so it is the same on every screen. The
// palette is the old app's, so imported lists look as they did.
const TagColors = {
  palette: [
    "#a8cfbb" , "#f8e08e" , "#8fb98f" , "#cba052" , "#c3dca2" , "#e7e3c6" , "#719949" ,
    "#dcd59a" , "#6fae91" , "#ae8643" , "#a6d2d2" , "#eccf7f" , "#9fbf7a" , "#cfd8cd" ,
  ],

  hashIndex( text ) {
    let hash = 0;
    for ( let i = 0 ; i < text.length ; i++ ) hash = ( hash * 31 + text.charCodeAt( i ) ) >>> 0;
    return hash % this.palette.length;
  },

  // vocab: [{name, color}] from the list document.
  of( name , vocab ) {
    const wanted = String( name || "" ).toLowerCase();
    const entry = ( vocab || [] ).find( ( tag ) => String( tag.name ).toLowerCase() === wanted );
    if ( entry && /^#[0-9a-f]{6}$/i.test( entry.color || "" ) ) return entry.color;
    return this.palette[ this.hashIndex( wanted ) ];
  },

  // The colour a new tag takes: the first one no tag is using yet.
  next( vocab ) {
    const used = new Set( ( vocab || [] ).map( ( tag ) => String( tag.color || "" ).toLowerCase() ) );
    return this.palette.find( ( color ) => !used.has( color ) ) || this.palette[ ( vocab || [] ).length % this.palette.length ];
  },

  // A chip element, painted. Styles go through the CSSOM: the CSP allows no
  // inline style attributes.
  paint( element , name , vocab ) {
    element.style.backgroundColor = this.of( name , vocab );
    element.style.color = "#20242c";
    return element;
  },
};
