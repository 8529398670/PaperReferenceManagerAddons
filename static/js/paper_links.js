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
// to a colour picked from its name, so it is the same on every screen.
//
// There are 14 slots. By default they are Wright State's colours
// (ThemePalettes.wsu in theme.js): its light ones as they are, its dark ones
// as tints, every one readable under the chips' dark text. Someone can switch
// to "theme" on Appearance (account tag_colors): the slots are then a
// gradient from the theme in use's accent to its second colour, lifted to
// pastels. What a list stores is always a slot's WSU colour, so a stored
// colour follows the slot into whichever palette is showing; a colour picked
// with the colour input is the reader's own and is used as it is.
const TagColors = {
  // From ThemePalettes.wsu, by slot. A tint is that colour mixed with white.
  wsu: [
    "#9bc3af" , "#f8e08e" , "#80a495" , "#cba052" , "#b1c79b" , "#e7e3c6" , "#719949" ,
    "#dcd59a" , "#75ad92" , "#ae8643" , "#b7babc" , "#e0c697" , "#94b276" , "#bfd1ca" ,
  ],
  // The palette before it was WSU's alone (the old app's), slot for slot, so
  // lists coloured then land on the same slots now.
  legacy: [
    "#a8cfbb" , "#f8e08e" , "#8fb98f" , "#cba052" , "#c3dca2" , "#e7e3c6" , "#719949" ,
    "#dcd59a" , "#6fae91" , "#ae8643" , "#a6d2d2" , "#eccf7f" , "#9fbf7a" , "#cfd8cd" ,
  ],
  // The old app's second, hidden palette ("pastel" skin, PALETTES.pastel in
  // its dashboard), slot for slot. Lists made under it stored these; they are
  // shown as the same slot of the palette in use, never as themselves.
  pastel: [
    "#bfd8f7" , "#c6e8e2" , "#c9e9c0" , "#e3eeb4" , "#f6e7ab" , "#fbd9b4" , "#f9c9c0" ,
    "#f4c3ce" , "#e9c6e8" , "#d3ccf3" , "#c6d2f0" , "#bfe4f2" , "#e0dac6" , "#dfe2e8" ,
  ],
  modes: [ "wsu" , "theme" ],
  mode: "wsu",
  cache: null,

  // The palette showing: WSU's, or the theme's gradient.
  get palette() {
    return this.mode === "theme" ? this.themed() : this.wsu;
  },

  // From /api/me, or the Appearance switch.
  setMode( mode ) {
    this.mode = this.modes.includes( mode ) ? mode : "wsu";
  },

  // Which slot a stored colour is, or -1 for a colour of the reader's own.
  slot( color ) {
    const wanted = String( color || "" ).toLowerCase();
    for ( const palette of [ this.wsu , this.legacy , this.pastel ] ) {
      const at = palette.indexOf( wanted );
      if ( at >= 0 ) return at;
    }
    return -1;
  },

  // The gradient for the theme in use, worked out once per set of colours.
  themed() {
    const theme = typeof Theme !== "undefined" && Theme.find ? Theme.find( Theme.current ) : null;
    const from = ( theme && theme.accent ) || ThemePalettes.wsu.green;
    const to = ( theme && theme.second ) || ThemePalettes.wsu.gold;
    const key = from + to;
    if ( this.cache && this.cache.key === key ) return this.cache.colors;
    const a = this.toOklch( from );
    const b = this.toOklch( to );
    // The short way round the hue circle; a grey end takes the other's hue.
    let ha = a.c < 0.02 ? b.h : a.h;
    let hb = b.c < 0.02 ? ha : b.h;
    if ( hb - ha > 180 ) ha += 360;
    else if ( ha - hb > 180 ) hb += 360;
    const count = this.wsu.length;
    const colors = [];
    for ( let i = 0 ; i < count ; i++ ) {
      const t = i / ( count - 1 );
      // Pastel, and a little lighter every other slot, so neighbours differ.
      const l = i % 2 ? 0.9 : 0.84;
      const c = Math.min( 0.08 , a.c + ( b.c - a.c ) * t );
      colors.push( this.fromOklch( l , c , ha + ( hb - ha ) * t ) );
    }
    this.cache = { key: key , colors: colors };
    return colors;
  },

  toOklch( hex ) {
    const lin = [ 1 , 3 , 5 ].map( ( at ) => {
      const v = parseInt( hex.substr( at , 2 ) , 16 ) / 255;
      return v <= 0.04045 ? v / 12.92 : Math.pow( ( v + 0.055 ) / 1.055 , 2.4 );
    } );
    const l = Math.cbrt( 0.4122214708 * lin[ 0 ] + 0.5363325363 * lin[ 1 ] + 0.0514459929 * lin[ 2 ] );
    const m = Math.cbrt( 0.2119034982 * lin[ 0 ] + 0.6806995451 * lin[ 1 ] + 0.1073969566 * lin[ 2 ] );
    const s = Math.cbrt( 0.0883024619 * lin[ 0 ] + 0.2817188376 * lin[ 1 ] + 0.6299787005 * lin[ 2 ] );
    const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
    const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
    const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
    return { l: L , c: Math.hypot( A , B ) , h: ( Math.atan2( B , A ) * 180 / Math.PI + 360 ) % 360 };
  },

  fromOklch( L , C , H ) {
    const h = ( ( H % 360 ) + 360 ) % 360 * Math.PI / 180;
    const A = C * Math.cos( h );
    const B = C * Math.sin( h );
    const l = Math.pow( L + 0.3963377774 * A + 0.2158037573 * B , 3 );
    const m = Math.pow( L - 0.1055613458 * A - 0.0638541728 * B , 3 );
    const s = Math.pow( L - 0.0894841775 * A - 1.2914855480 * B , 3 );
    const lin = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ];
    return "#" + lin.map( ( v ) => {
      const x = Math.min( 1 , Math.max( 0 , v ) );
      const srgb = x <= 0.0031308 ? x * 12.92 : 1.055 * Math.pow( x , 1 / 2.4 ) - 0.055;
      return Math.round( srgb * 255 ).toString( 16 ).padStart( 2 , "0" );
    } ).join( "" );
  },

  hashIndex( text ) {
    let hash = 0;
    for ( let i = 0 ; i < text.length ; i++ ) hash = ( hash * 31 + text.charCodeAt( i ) ) >>> 0;
    return hash % this.wsu.length;
  },

  // vocab: [{name, color}] from the list document.
  of( name , vocab ) {
    const wanted = String( name || "" ).toLowerCase();
    const entry = ( vocab || [] ).find( ( tag ) => String( tag.name ).toLowerCase() === wanted );
    if ( entry && /^#[0-9a-f]{6}$/i.test( entry.color || "" ) ) {
      const at = this.slot( entry.color );
      return at >= 0 ? this.palette[ at ] : entry.color;
    }
    return this.palette[ this.hashIndex( wanted ) ];
  },

  // The colour a new tag takes: the first slot no tag is using yet, as the
  // WSU colour that is stored.
  next( vocab ) {
    const used = new Set( ( vocab || [] ).map( ( tag ) => this.slot( tag.color ) ) );
    const free = this.wsu.findIndex( ( color , at ) => !used.has( at ) );
    return this.wsu[ free >= 0 ? free : ( vocab || [] ).length % this.wsu.length ];
  },

  // A chip element, painted. Styles go through the CSSOM: the CSP allows no
  // inline style attributes.
  paint( element , name , vocab ) {
    element.style.backgroundColor = this.of( name , vocab );
    element.style.color = "#20242c";
    return element;
  },
};
