// Reading a CSV into a list: the old app's parseCSV, and its docFromCSV turned
// into a PLAN of ops, so an import is one batch (one undo step) like any
// other change instead of a whole document posted over the list.
//
// Columns are recognised by name: key / DOI_or_Key, DOI, title, year,
// journal, author(s), tags (and modalities / section tags). #, Cite and
// MD_File are DERIVED, so they are read past: re-importing an export never
// turns them into free-text columns. Any other column becomes a free-text
// column of the list (a new one arrives folded).
//
// merge (the default): new papers are added; a paper already here only gains
//   the tags it lacks and fills its empty cells.
// replace: the list becomes the file's rows, in the file's order, with the
//   file's tags and cells. The staging shelf is left alone.
const ListCSV = {
  H_NUM: /^#$|^no\.?$|^rank$/i,
  H_KEY: /^(doi[_ ]?or[_ ]?key|key)$/i,
  H_DOI: /^doi$/i,
  H_TITLE: /^title$/i,
  H_YEAR: /^year$/i,
  H_JOURNAL: /^(journal|venue|source|publication)$/i,
  H_AUTHORS: /^authors?$/i,
  H_TAGS: /^(tags?|modalit\w*|section[_ ]?tags?)$/i,
  H_MD: /^md[_ ]?file$/i,
  H_CITE: /^(cite|citation|in[-_ ]?text([-_ ]?citation)?)$/i,
  // A tier board's export says each row's tier; read back onto one, it puts
  // the row there. Anywhere else it is derived, and read past.
  H_TIER: /^(tier|section)$/i,

  parse( text ) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    let i = 0;
    text = text.replace( /^﻿/ , "" ).replace( /\r\n/g , "\n" ).replace( /\r/g , "\n" );
    while ( i < text.length ) {
      const c = text[ i ];
      if ( quoted ) {
        if ( c === '"' ) {
          if ( text[ i + 1 ] === '"' ) {
            field += '"';
            i += 2;
            continue;
          }
          quoted = false;
          i++;
          continue;
        }
        field += c;
        i++;
        continue;
      }
      if ( c === '"' ) quoted = true;
      else if ( c === "," ) {
        row.push( field );
        field = "";
      } else if ( c === "\n" ) {
        row.push( field );
        field = "";
        rows.push( row );
        row = [];
      } else field += c;
      i++;
    }
    if ( field.length || row.length ) {
      row.push( field );
      rows.push( row );
    }
    return rows.filter( ( r ) => r.some( ( cell ) => String( cell ).trim().length ) );
  },

  splitTags( text ) {
    return String( text || "" ).split( /[;,|]/ ).map( ( tag ) => tag.trim() ).filter( Boolean );
  },

  slug( text ) {
    return String( text || "" ).normalize( "NFKD" ).toLowerCase().replace( /[^a-z0-9]+/g , "-" ).replace( /^-+|-+$/g , "" );
  },

  normDoi( text ) {
    const match = String( text || "" ).match( /10\.\d{4,9}\/\S+/ );
    return match ? match[ 0 ].replace( /[.;:,)]+$/ , "" ) : "";
  },

  // -> { ops , counts: { new , updated , unchanged , removed } , columns: [ new labels ] , rows }
  plan( rows , doc , mode ) {
    if ( rows.length < 2 ) throw new Error( I18n.get( "lists.csv_empty" ) );
    const head = rows[ 0 ].map( ( h ) => String( h || "" ).trim() );
    const at = { key: -1 , doi: -1 , title: -1 , year: -1 , journal: -1 , authors: -1 , tier: -1 };
    const tagCols = [];
    const extra = [];
    head.forEach( ( h , i ) => {
      if ( this.H_KEY.test( h ) ) at.key = i;
      else if ( this.H_DOI.test( h ) ) at.doi = i;
      else if ( this.H_TITLE.test( h ) ) at.title = i;
      else if ( this.H_YEAR.test( h ) ) at.year = i;
      else if ( this.H_JOURNAL.test( h ) ) at.journal = i;
      else if ( this.H_AUTHORS.test( h ) ) at.authors = i;
      else if ( this.H_TAGS.test( h ) ) tagCols.push( i );
      else if ( this.H_TIER.test( h ) ) at.tier = i;
      else if ( this.H_MD.test( h ) || this.H_NUM.test( h ) || this.H_CITE.test( h ) ) { /* derived: not stored */ }
      else if ( h ) extra.push( { i: i , label: h } );
    } );
    if ( at.key < 0 && at.doi < 0 && at.title < 0 ) throw new Error( I18n.get( "lists.csv_no_ids" ) );

    const lower = ( text ) => String( text || "" ).toLowerCase();
    const columns = doc.columns || [];
    const ops = [];
    const newColumns = [];
    extra.forEach( ( column ) => {
      const have = columns.find( ( c ) => lower( c.label ) === lower( column.label ) ) || columns.find( ( c ) => c.id === this.slug( column.label ) );
      if ( have ) {
        column.col = have.label;
      } else {
        column.col = column.label;
        newColumns.push( column.label );
      }
    } );
    if ( columns.length + newColumns.length > 16 ) throw new Error( I18n.get( "lists.csv_too_many_columns" ) );
    newColumns.forEach( ( label ) => {
      ops.push( { op: "column_add" , label: label } );
      ops.push( { op: "column_fold" , col: label , folded: true } );
    } );

    const byKey = new Map();
    const byTitle = new Map();
    ( doc.items || [] ).forEach( ( item ) => {
      byKey.set( lower( item.key ) , item );
      if ( item.doi ) byKey.set( lower( item.doi ) , item );
      if ( item.title ) byTitle.set( this.slug( item.title ) , item );
    } );

    const counts = { new: 0 , updated: 0 , unchanged: 0 , removed: 0 };
    const order = [];
    const seen = new Set();
    const tagAdds = new Map();
    const tagRemoves = new Map();
    const push = ( map , tag , key ) => {
      if ( !map.has( tag ) ) map.set( tag , [] );
      map.get( tag ).push( key );
    };
    const vocab = new Set( ( ( doc.vocab && doc.vocab.tags ) || [] ).map( ( tag ) => lower( tag.name ) ) );
    const newTags = new Map();
    const sections = doc.sections || [];
    const tierOf = ( text ) => sections.find( ( section ) => lower( section.label ) === lower( text ) || section.id === lower( text ) ) || null;
    const tiers = new Map();

    rows.slice( 1 ).forEach( ( row ) => {
      const cell = ( i ) => ( i >= 0 && i < row.length ? String( row[ i ] ).trim() : "" );
      const title = cell( at.title );
      const doi = this.normDoi( cell( at.doi ) ) || this.normDoi( cell( at.key ) );
      let key = cell( at.key ) || doi;
      const alias = lower( key ).replace( /^zotero:/ , "nodoi-zotero-" );
      const existing = ( key && ( byKey.get( lower( key ) ) || byKey.get( alias ) ) ) || ( !key && title && byTitle.get( this.slug( title ) ) ) || null;
      if ( !key ) key = existing ? existing.key : "ref-" + ( this.slug( title ).slice( 0 , 80 ) || "unknown" );
      if ( existing ) key = existing.key;
      if ( seen.has( lower( key ) ) ) return;
      seen.add( lower( key ) );
      order.push( key );
      const tier = sections.length ? tierOf( cell( at.tier ) ) : null;
      const tierMoves = tier && ( !existing || existing.section !== tier.id || mode === "replace" );
      if ( tierMoves ) push( tiers , tier.id , key );
      let tags = [];
      tagCols.forEach( ( i ) => { tags = tags.concat( this.splitTags( cell( i ) ) ); } );
      tags.forEach( ( tag ) => {
        if ( !vocab.has( lower( tag ) ) && !newTags.has( lower( tag ) ) ) newTags.set( lower( tag ) , tag );
      } );
      const cells = {};
      extra.forEach( ( column ) => {
        const value = cell( column.i );
        if ( value ) cells[ column.col ] = value;
      } );

      if ( !existing ) {
        const paper = { key: key , title: title || key , doi: doi };
        const year = parseInt( cell( at.year ) , 10 );
        if ( Number.isFinite( year ) ) paper.year = year;
        if ( cell( at.journal ) ) paper.journal = cell( at.journal );
        if ( cell( at.authors ) ) paper.authors = cell( at.authors );
        const op = { op: "add" , paper: paper , if_absent: true , auto_tag: false , prefill: false , at: "bottom" };
        if ( tags.length ) op.tags = tags;
        if ( Object.keys( cells ).length ) op.cells = cells;
        ops.push( op );
        counts.new += 1;
        return;
      }
      let touched = false;
      const has = new Set( ( existing.tags || [] ).map( lower ) );
      tags.forEach( ( tag ) => {
        if ( !has.has( lower( tag ) ) ) {
          push( tagAdds , tag , key );
          touched = true;
        }
      } );
      if ( mode === "replace" ) {
        const wanted = new Set( tags.map( lower ) );
        ( existing.tags || [] ).forEach( ( tag ) => {
          if ( !wanted.has( lower( tag ) ) ) {
            push( tagRemoves , tag , key );
            touched = true;
          }
        } );
      }
      const fields = existing.fields || {};
      Object.entries( cells ).forEach( ( [ col , value ] ) => {
        const column = columns.find( ( c ) => c.label === col );
        const now = column ? fields[ column.id ] || "" : "";
        // An export joins a cell's lines with "; ": reading it back is no change.
        if ( now === value || now.split( "\n" ).map( ( line ) => line.trim() ).filter( Boolean ).join( "; " ) === value ) return;
        if ( mode !== "replace" && now ) return;
        ops.push( { op: "set_cell" , row: key , col: col , value: value } );
        touched = true;
      } );
      if ( touched || tierMoves ) counts.updated += 1;
      else counts.unchanged += 1;
    } );

    tagAdds.forEach( ( keys , tag ) => ops.push( { op: "tag" , rows: keys , add: [ tag ] } ) );
    tagRemoves.forEach( ( keys , tag ) => ops.push( { op: "tag" , rows: keys , remove: [ tag ] } ) );
    if ( mode === "replace" ) {
      const keep = new Set( order.map( lower ) );
      const gone = ( doc.items || [] ).filter( ( item ) => !keep.has( lower( item.key ) ) ).map( ( item ) => item.key );
      counts.removed = gone.length;
      if ( gone.length ) ops.unshift( { op: "remove" , rows: gone } );
      if ( order.length ) ops.push( { op: "reorder" , rows: order , at: 1 } );
    }
    tiers.forEach( ( keys , section ) => ops.push( { op: "section_set" , rows: keys , section: section } ) );
    // A tag new to the list takes a colour of its own, as one made by hand does.
    const created = [];
    const palette = ( ( doc.vocab && doc.vocab.tags ) || [] ).slice();
    newTags.forEach( ( name ) => {
      const color = TagColors.next( palette );
      palette.push( { name: name , color: color } );
      created.push( { op: "tag_create" , name: name , color: color } );
    } );
    return { ops: created.concat( ops ) , counts: counts , columns: newColumns , rows: rows.length - 1 };
  },
};
