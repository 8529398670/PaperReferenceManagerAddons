// Import from a Google Sheet (or a CSV downloaded from one), column by column.
//
// The server reads the sheet (POST /api/sheet/csv: docs.google.com only, by
// its ID) and the links behind its cells; the links are written into the
// cells' text here, line by line, so a "Datasets" label arrives as its URL.
// Then the old app's sheet merge (mergeSheet in sort.html), turned into a
// PLAN of ops so the import is one batch and one undo step:
//
//   * a paper the sheet has and the list hasn't is added, with everything
//     the dialog brings in;
//   * a paper both have takes the sheet's text in each chosen column: fill
//     only where the list's cell is empty, overwrite wherever they differ;
//     and its tags: add the missing ones, or replace them with the sheet's.
//     The sheet has to SAY something: an empty cell there never clears one
//     here;
//   * a paper on the staging shelf that the sheet lists moves onto the list;
//   * nothing is removed. With the sheet's order, a paper only this list has
//     rides under the row it is under now.
const ListSheet = {
  lists: null,
  // The sheet's own columns that are somebody else's notes: off by default.
  H_SKIP: /^(notes?|added[_ ]?by|methods?[_ ]?evidence)$/i,

  init( lists ) {
    this.lists = lists;
  },

  // ---- the links behind the cells ----------------------------------------------------

  fold( text ) {
    return String( text || "" ).normalize( "NFD" ).replace( /[̀-ͯ]/g , "" ).toLowerCase();
  },

  // A name with its link, or just the link when the name says nothing the URL
  // doesn't (ops.link_line).
  linkLine( label , url ) {
    label = String( label || "" ).trim();
    const u = this.fold( url );
    const words = label.normalize( "NFKD" ).toLowerCase().replace( /^hf:/ , "" )
      .split( /[^a-z0-9]+/ ).filter( ( word ) => word && !/^(www|https?)$/.test( word ) );
    return words.every( ( word ) => u.includes( word ) ) ? url : label + " — " + url;
  },

  // A cell's runs ([ text , url|null ], from the server) as its text with the
  // links written in, line for line. A line with no link stays as it was.
  linkedCell( runs ) {
    const lines = [ [] ];
    runs.forEach( ( [ text , url ] ) => String( text || "" ).split( "\n" ).forEach( ( piece , k ) => {
      if ( k ) lines.push( [] );
      if ( piece ) lines[ lines.length - 1 ].push( [ piece , url || "" ] );
    } ) );
    return lines.map( ( segs ) => {
      const urls = Array.from( new Set( segs.map( ( seg ) => seg[ 1 ] ).filter( Boolean ) ) );
      if ( urls.length > 1 ) return segs.map( ( [ t , u ] ) => ( u ? this.linkLine( t , u ) : t ) ).join( "" );
      const text = segs.map( ( seg ) => seg[ 0 ] ).join( "" );
      return urls.length ? this.linkLine( text , urls[ 0 ] ) : text;
    } ).join( "\n" );
  },

  // The columns: which say what paper a row is, which are tags, which are free
  // text (only those take links).
  columns( head ) {
    const ix = { key: -1 , doi: -1 , title: -1 , year: -1 , tags: [] , extra: [] };
    head.forEach( ( h , i ) => {
      if ( ListCSV.H_KEY.test( h ) ) ix.key = i;
      else if ( ListCSV.H_DOI.test( h ) ) ix.doi = i;
      else if ( ListCSV.H_TITLE.test( h ) ) ix.title = i;
      else if ( ListCSV.H_YEAR.test( h ) ) ix.year = i;
      else if ( ListCSV.H_TAGS.test( h ) ) ix.tags.push( i );
      else if ( ListCSV.H_MD.test( h ) || ListCSV.H_NUM.test( h ) || ListCSV.H_CITE.test( h ) || ListCSV.H_TIER.test( h ) ) { /* derived */ }
      else if ( h ) ix.extra.push( { i: i , label: h } );
    } );
    return ix;
  },

  // -> { byCol: { column index: cells linked } }
  applyLinks( rows , links ) {
    const byCol = {};
    if ( !links ) return byCol;
    const free = new Set( this.columns( rows[ 0 ].map( ( h ) => String( h || "" ).trim() ) ).extra.map( ( x ) => x.i ) );
    links.forEach( ( cells , r ) => {
      if ( !r || !cells || !rows[ r ] ) return;
      Object.keys( cells ).forEach( ( j ) => {
        if ( !free.has( +j ) ) return;
        rows[ r ][ j ] = this.linkedCell( cells[ j ] );
        byCol[ j ] = ( byCol[ j ] || 0 ) + 1;
      } );
    } );
    return byCol;
  },

  // ---- the plan ------------------------------------------------------------------------

  // how = { cols: { header index: "fill" | "over" } , tags: "" | "merge" | "replace" ,
  //         order: "list" | "sheet" , url }
  // -> { ops , n } where n counts, for papers already here, what each choice
  //    WOULD touch whatever it is set to (the dialog's notes).
  plan( rows , doc , how ) {
    const lower = ( text ) => String( text || "" ).toLowerCase();
    const head = rows[ 0 ].map( ( h ) => String( h || "" ).trim() );
    const ix = this.columns( head );
    const columns = doc.columns || [];
    const items = doc.items || [];
    const staging = doc.staging || [];
    const ops = [];
    // A chosen column lands in the list's column of the same name; a new one
    // is added folded, so the list keeps its width until asked.
    const take = ix.extra.map( ( x ) => {
      const have = columns.find( ( c ) => c.id === ListCSV.slug( x.label ) || lower( c.label ) === lower( x.label ) );
      return { i: x.i , label: have ? have.label : x.label , id: have ? have.id : null , mode: how.cols[ x.i ] || "" };
    } );
    take.filter( ( c ) => c.mode && !c.id ).forEach( ( c ) => {
      ops.push( { op: "column_add" , label: c.label } );
      ops.push( { op: "column_fold" , col: c.label , folded: true } );
    } );
    if ( columns.length + take.filter( ( c ) => c.mode && !c.id ).length > 16 ) throw new Error( I18n.get( "lists.csv_too_many_columns" ) );
    // "fmri" in the sheet is the list's "fMRI".
    const canon = new Map( ( ( doc.vocab && doc.vocab.tags ) || [] ).map( ( tag ) => [ lower( tag.name ) , tag.name ] ) );
    const fresh = new Map();
    const tagName = ( tag ) => {
      if ( !canon.has( lower( tag ) ) ) {
        canon.set( lower( tag ) , tag );
        fresh.set( lower( tag ) , tag );
      }
      return canon.get( lower( tag ) );
    };
    // Every way the list knows a paper: key, DOI, the sheet's zotero:KEY, title.
    const known = new Map();
    const index = ( item ) => {
      const put = ( k ) => { if ( k && !known.has( k ) ) known.set( k , item ); };
      put( lower( item.key ) );
      if ( item.doi ) put( "doi:" + lower( item.doi ) );
      if ( /^10\./.test( item.key || "" ) ) put( "doi:" + lower( item.key ) );
      const zotero = /^nodoi-zotero-(.+)$/i.exec( item.key || "" );
      if ( zotero ) put( lower( "zotero:" + zotero[ 1 ] ) );
      const title = ListCSV.slug( item.title );
      if ( title ) put( "t:" + title );
    };
    items.forEach( index );
    staging.forEach( index );
    const onList = new Set( items.map( ( item ) => item.key ) );
    const onShelf = new Set( staging.map( ( item ) => item.key ) );
    const cell = ( row , i ) => ( i >= 0 && i < row.length ? String( row[ i ] ).trim() : "" );
    const n = { added: 0 , have: 0 , shelf: 0 , filled: 0 , replaced: 0 , kept: 0 , tagged: 0 , col: {} , tagGain: 0 , tagDiffer: 0 };
    const seq = [];
    const took = new Set();
    const shelfKeys = [];
    const tagAdds = new Map();
    const tagRemoves = new Map();
    const push = ( map , tag , key ) => {
      if ( !map.has( tag ) ) map.set( tag , [] );
      map.get( tag ).push( key );
    };
    rows.slice( 1 ).forEach( ( row ) => {
      const key = cell( row , ix.key );
      const title = cell( row , ix.title );
      const doi = ListCSV.normDoi( cell( row , ix.doi ) ) || ( /^10\./.test( key ) ? key : "" );
      if ( !key && !doi && !title ) return;
      const item = ( key && known.get( lower( key ) ) ) || ( doi && known.get( "doi:" + lower( doi ) ) ) || ( title && known.get( "t:" + ListCSV.slug( title ) ) ) || null;
      const want = [];
      ix.tags.forEach( ( i ) => ListCSV.splitTags( cell( row , i ) ).forEach( ( tag ) => {
        if ( !want.some( ( have ) => lower( have ) === lower( tag ) ) ) want.push( tag );
      } ) );
      if ( !item ) {
        const newKey = key || doi || "loose-" + ( ListCSV.slug( title ).slice( 0 , 80 ) || "row" );
        if ( took.has( lower( newKey ) ) ) return;
        took.add( lower( newKey ) );
        const paper = { key: newKey , title: title || newKey , doi: doi };
        const year = parseInt( cell( row , ix.year ) , 10 );
        if ( Number.isFinite( year ) ) paper.year = year;
        const op = { op: "add" , paper: paper , if_absent: true , auto_tag: false , prefill: false , at: "bottom" };
        if ( how.tags && want.length ) op.tags = want.map( tagName );
        const cells = {};
        take.forEach( ( c ) => {
          const value = cell( row , c.i );
          if ( c.mode && value ) cells[ c.label ] = value;
        } );
        if ( Object.keys( cells ).length ) op.cells = cells;
        ops.push( op );
        index( { key: newKey , doi: doi , title: title } );
        n.added += 1;
        seq.push( newKey );
        return;
      }
      if ( took.has( lower( item.key ) ) ) return;
      took.add( lower( item.key ) );
      n.have += 1;
      if ( onShelf.has( item.key ) ) {
        n.shelf += 1;
        shelfKeys.push( item.key );
      }
      const has = ( tag ) => ( item.tags || [] ).some( ( mine ) => lower( mine ) === lower( tag ) );
      const gain = want.filter( ( tag ) => !has( tag ) );
      const differ = gain.length > 0 || ( want.length > 0 && ( item.tags || [] ).some( ( mine ) => !want.some( ( tag ) => lower( tag ) === lower( mine ) ) ) );
      if ( gain.length ) n.tagGain += 1;
      if ( differ ) n.tagDiffer += 1;
      if ( how.tags === "merge" && gain.length ) {
        gain.forEach( ( tag ) => push( tagAdds , tagName( tag ) , item.key ) );
        n.tagged += 1;
      } else if ( how.tags === "replace" && differ ) {
        gain.forEach( ( tag ) => push( tagAdds , tagName( tag ) , item.key ) );
        ( item.tags || [] ).filter( ( mine ) => !want.some( ( tag ) => lower( tag ) === lower( mine ) ) ).forEach( ( mine ) => push( tagRemoves , mine , item.key ) );
        n.tagged += 1;
      }
      take.forEach( ( c ) => {
        const value = cell( row , c.i );
        if ( !value ) return;
        const was = String( ( c.id && item.fields && item.fields[ c.id ] ) || "" ).trim();
        const stat = n.col[ c.i ] = n.col[ c.i ] || { fill: 0 , differ: 0 };
        // An export joins a cell's lines with "; ": reading it back is no change.
        const same = was === value || was.split( "\n" ).map( ( line ) => line.trim() ).filter( Boolean ).join( "; " ) === value;
        if ( !was ) {
          stat.fill += 1;
          if ( c.mode ) {
            ops.push( { op: "set_cell" , row: item.key , col: c.label , value: value } );
            n.filled += 1;
          }
        } else if ( !same ) {
          stat.differ += 1;
          if ( c.mode === "over" ) {
            ops.push( { op: "set_cell" , row: item.key , col: c.label , value: value } );
            n.replaced += 1;
          } else if ( c.mode ) {
            n.kept += 1;
          }
        }
      } );
      seq.push( item.key );
    } );
    tagAdds.forEach( ( keys , tag ) => ops.push( { op: "tag" , rows: keys , add: [ tag ] } ) );
    tagRemoves.forEach( ( keys , tag ) => ops.push( { op: "tag" , rows: keys , remove: [ tag ] } ) );
    if ( shelfKeys.length ) ops.push( { op: "stage_add" , rows: shelfKeys , at: "bottom" } );
    // The order: the list's, the new ones on the end in the sheet's order; or
    // the sheet's, each paper only the list has under the row it is under now.
    const inSheet = new Set( seq );
    let order;
    if ( how.order === "sheet" ) {
      const lead = [];
      const under = new Map();
      let anchor = null;
      items.forEach( ( item ) => {
        if ( inSheet.has( item.key ) ) {
          anchor = item.key;
          return;
        }
        if ( !anchor ) lead.push( item.key );
        else {
          if ( !under.has( anchor ) ) under.set( anchor , [] );
          under.get( anchor ).push( item.key );
        }
      } );
      order = lead.concat( ...seq.map( ( key ) => [ key ].concat( under.get( key ) || [] ) ) );
    } else {
      order = items.map( ( item ) => item.key ).concat( seq.filter( ( key ) => !onList.has( key ) ) );
    }
    n.moves = this.moves( items.map( ( item ) => item.key ) , order );
    const now = items.map( ( item ) => item.key ).concat( seq.filter( ( key ) => !onList.has( key ) ) );
    if ( order.join( "\n" ) !== now.join( "\n" ) || shelfKeys.length ) ops.push( { op: "reorder" , rows: order , at: 1 } );
    if ( how.url && how.url !== ( ( doc.options && doc.options.sheet_url ) || "" ) ) ops.push( { op: "options" , sheet_url: how.url } );
    // A tag new to the list takes a colour of its own, as one made by hand does.
    const palette = ( ( doc.vocab && doc.vocab.tags ) || [] ).slice();
    const created = [];
    if ( how.tags ) {
      fresh.forEach( ( name ) => {
        const color = TagColors.next( palette );
        palette.push( { name: name , color: color } );
        created.push( { op: "tag_create" , name: name , color: color } );
      } );
    }
    return { ops: created.concat( ops ) , n: n };
  },

  // How many of the papers already here a new order MOVES: all of them but the
  // longest run the two orders agree on, so one paper dragged from the bottom
  // to the top counts as one.
  moves( before , after ) {
    const now = new Map( before.map( ( key , i ) => [ key , i ] ) );
    const seq = after.map( ( key ) => now.get( key ) ).filter( ( i ) => i !== undefined );
    const tails = [];
    seq.forEach( ( x ) => {
      let lo = 0;
      let hi = tails.length;
      while ( lo < hi ) {
        const mid = ( lo + hi ) >> 1;
        if ( tails[ mid ] < x ) lo = mid + 1;
        else hi = mid;
      }
      tails[ lo ] = x;
    } );
    return seq.length - tails.length;
  },

  // ---- the dialog ------------------------------------------------------------------------

  open() {
    const lists = this.lists;
    const state = { url: ( lists.view.doc.options && lists.view.doc.options.sheet_url ) || "" , rows: null , byCol: {} , why: "" , name: "" ,
      cols: {} , tags: "merge" , order: "list" , reading: false };
    const url = Dom.el( "input" , { class: "form-control" , attrs: { type: "url" , id: "list-sheet-url" , placeholder: "https://docs.google.com/spreadsheets/d/…" } } );
    url.value = state.url;
    const file = Dom.el( "input" , { class: "form-control" , attrs: { type: "file" , accept: ".csv,text/csv" , "aria-label": I18n.get( "lists.sheet_file" ) } } );
    const take = ( rows , name , sheetUrl , links , why ) => {
      if ( rows.length < 2 ) throw new Error( I18n.get( "lists.csv_empty" ) );
      const ix = this.columns( rows[ 0 ].map( ( h ) => String( h || "" ).trim() ) );
      if ( ix.key < 0 && ix.doi < 0 && ix.title < 0 ) throw new Error( I18n.get( "lists.csv_no_ids" ) );
      state.byCol = this.applyLinks( rows , links );
      state.why = why || "";
      state.rows = rows;
      state.name = name;
      state.url = sheetUrl;
      state.cols = {};
      ix.extra.forEach( ( x ) => { if ( !this.H_SKIP.test( x.label ) ) state.cols[ x.i ] = "fill"; } );
      state.tags = ix.tags.length ? "merge" : "";
    };
    const read = async () => {
      ListModal.problem( "" );
      const link = url.value.trim();
      if ( !link ) return;
      state.reading = true;
      ListModal.redraw();
      try {
        const answer = await Api.post( "/api/sheet/csv" , { url: link } );
        take( answer.rows , I18n.get( "lists.sheet_the_sheet" ) , link , answer.links , answer.links_error || ( answer.links ? "" : I18n.get( "lists.sheet_no_links" ) ) );
      } catch ( error ) {
        ListModal.problem( error.message );
      }
      state.reading = false;
      ListModal.redraw();
    };
    url.addEventListener( "keydown" , ( event ) => {
      if ( event.key === "Enter" ) {
        event.preventDefault();
        read();
      }
    } );
    file.addEventListener( "change" , async () => {
      ListModal.problem( "" );
      if ( !file.files.length ) return;
      try {
        take( ListCSV.parse( await file.files[ 0 ].text() ) , file.files[ 0 ].name , "" , null , "" );
      } catch ( error ) {
        ListModal.problem( error.message );
      }
      ListModal.redraw();
    } );
    const apply = async () => {
      ListModal.problem( "" );
      let planned;
      try {
        planned = this.plan( state.rows , lists.view.doc , { cols: state.cols , tags: state.tags , order: state.order , url: state.url } );
      } catch ( error ) {
        ListModal.problem( error.message );
        return;
      }
      if ( planned.ops.length === 0 ) {
        ListModal.problem( I18n.get( "lists.sheet_nothing" ) );
        return;
      }
      try {
        await Api.post( "/api/lists/" + encodeURIComponent( lists.slug ) + "/ops" , { ops: planned.ops , dry_run: true } );
      } catch ( error ) {
        ListModal.problem( error.message + ( error.payload && error.payload.index !== undefined ? " (" + JSON.stringify( error.payload.op ).slice( 0 , 160 ) + ")" : "" ) );
        return;
      }
      const answer = await lists.changeWhole( "undo.list_sheet" , planned.ops , { toast: false } );
      if ( !answer ) return;
      ListModal.close();
      const k = planned.n;
      const parts = [ I18n.get( "lists.sheet_done_added" ).replace( "{count}" , k.added ) ];
      if ( k.shelf ) parts.push( I18n.get( "lists.sheet_done_shelf" ).replace( "{count}" , k.shelf ) );
      if ( k.tagged ) parts.push( I18n.get( "lists.sheet_done_tagged" ).replace( "{count}" , k.tagged ) );
      if ( k.filled ) parts.push( I18n.get( "lists.sheet_done_filled" ).replace( "{count}" , k.filled ) );
      if ( k.replaced ) parts.push( I18n.get( "lists.sheet_done_replaced" ).replace( "{count}" , k.replaced ) );
      if ( k.kept ) parts.push( I18n.get( "lists.sheet_done_kept" ).replace( "{count}" , k.kept ) );
      Dom.toast( parts.join( " · " ) , "ok" , { text: I18n.get( "undo.button" ) , run: () => Undo.undo() } );
    };
    ListModal.open( I18n.get( "lists.sheet_title" ) , () => {
      const readButton = Dom.el( "button" , { class: "btn btn-outline-primary" , attrs: { type: "button" } , text: I18n.get( state.reading ? "lists.sheet_reading" : "lists.sheet_read" ) , on: { click: read } } );
      readButton.disabled = state.reading;
      const body = [
        Dom.el( "label" , { class: "form-label" , text: I18n.get( "lists.sheet_url" ) , attrs: { for: "list-sheet-url" } } ),
        Dom.el( "div" , { class: "input-group" , children: [ url , readButton ] } ),
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.sheet_help" ) } ),
        Dom.el( "details" , { class: "small mb-2" , children: [ Dom.el( "summary" , { text: I18n.get( "lists.sheet_file" ) } ) , file ] } ),
      ];
      if ( !state.rows ) return { body: body };
      const head = state.rows[ 0 ].map( ( h ) => String( h || "" ).trim() );
      const ix = this.columns( head );
      // One dry run with every column filled and tags merged labels every choice:
      // a column's counts don't depend on what the others are set to.
      const all = {};
      ix.extra.forEach( ( x ) => { all[ x.i ] = "fill"; } );
      const dry = this.plan( state.rows , lists.view.doc , { cols: all , tags: "merge" , order: "list" } ).n;
      const moves = this.plan( state.rows , lists.view.doc , { cols: {} , tags: "" , order: "sheet" } ).n.moves;
      const stat = ( i ) => dry.col[ i ] || { fill: 0 , differ: 0 };
      const note = ( mode , st ) => {
        if ( !mode ) return I18n.get( "lists.sheet_left_out" );
        let text = I18n.get( "lists.sheet_note_fill" ).replace( "{count}" , st.fill );
        if ( st.differ ) text += " · " + I18n.get( mode === "over" ? "lists.sheet_note_over" : "lists.sheet_note_keep" ).replace( "{count}" , st.differ );
        return text;
      };
      const select = ( id , options , value , change ) => {
        const element = Dom.el( "select" , { class: "form-select form-select-sm" , attrs: { id: id } } );
        options.forEach( ( [ v , key ] ) => element.appendChild( Dom.el( "option" , { text: I18n.get( key ) , attrs: { value: v } } ) ) );
        element.value = value;
        element.addEventListener( "change" , () => {
          change( element.value );
          ListModal.redraw();
        } );
        return element;
      };
      const choice = ( id , label , control , text , warn ) => Dom.el( "div" , { class: "row g-2 align-items-center py-1 border-bottom" , children: [
        Dom.el( "div" , { class: "col-12 col-md-4" , children: [ Dom.el( "label" , { class: "fw-semibold small" , text: label , attrs: { for: id } } ) ] } ),
        Dom.el( "div" , { class: "col-12 col-md-3" , children: [ control ] } ),
        Dom.el( "div" , { class: "col-12 col-md-5 small " + ( warn ? "text-warning-emphasis" : "text-body-secondary" ) , text: text } ),
      ] } );
      const colModes = [ [ "" , "lists.sheet_mode_out" ] , [ "fill" , "lists.sheet_mode_fill" ] , [ "over" , "lists.sheet_mode_over" ] ];
      const tagModes = [ [ "" , "lists.sheet_mode_out" ] , [ "merge" , "lists.sheet_tags_merge" ] , [ "replace" , "lists.sheet_tags_replace" ] ];
      const choices = [];
      if ( ix.tags.length ) {
        const text = !state.tags ? I18n.get( "lists.sheet_left_out" ) : I18n.get( state.tags === "replace" ? "lists.sheet_note_tags_replace" : "lists.sheet_note_tags_merge" ).replace( "{count}" , state.tags === "replace" ? dry.tagDiffer : dry.tagGain );
        choices.push( choice( "list-sheet-tags" , I18n.get( "lists.col_tags" ) , select( "list-sheet-tags" , tagModes , state.tags , ( v ) => { state.tags = v; } ) , text , state.tags === "replace" ) );
      }
      ix.extra.forEach( ( x ) => {
        const mode = state.cols[ x.i ] || "";
        const id = "list-sheet-col-" + x.i;
        choices.push( choice( id , x.label , select( id , colModes , mode , ( v ) => {
          if ( v ) state.cols[ x.i ] = v;
          else delete state.cols[ x.i ];
        } ) , note( mode , stat( x.i ) ) , mode === "over" ) );
      } );
      const linked = Object.keys( state.byCol ).map( ( i ) => head[ i ] + " " + state.byCol[ i ] );
      let linkNote = "";
      if ( !state.url ) linkNote = I18n.get( "lists.sheet_links_file" );
      else if ( linked.length ) linkNote = I18n.get( "lists.sheet_links_in" ).replace( "{cells}" , () => linked.join( " · " ) );
      else if ( state.why ) linkNote = I18n.get( "lists.sheet_links_failed" ).replace( "{why}" , () => state.why );
      const radio = ( value , key , extra ) => {
        const input = Dom.el( "input" , { class: "form-check-input" , attrs: { type: "radio" , name: "list-sheet-order" , id: "list-sheet-order-" + value } } );
        input.checked = state.order === value;
        input.addEventListener( "change" , () => {
          state.order = value;
          ListModal.redraw();
        } );
        return Dom.el( "div" , { class: "form-check" , children: [ input , Dom.el( "label" , { class: "form-check-label" , text: I18n.get( key ) + ( extra ? " " + extra : "" ) , attrs: { for: input.id } } ) ] } );
      };
      const count = ( lists.view.doc.items || [] ).length;
      body.push(
        Dom.el( "p" , { class: "fw-semibold mt-3 mb-1" , text: I18n.get( "lists.sheet_summary" ).replace( "{name}" , () => state.name ).replace( "{added}" , dry.added ).replace( "{have}" , dry.have - dry.shelf )
          + ( dry.shelf ? " " + I18n.get( "lists.sheet_summary_shelf" ).replace( "{count}" , dry.shelf ) : "" ) } ),
        Dom.el( "p" , { class: "small" , text: I18n.get( "lists.sheet_add_only" ) } ),
      );
      if ( linkNote ) body.push( Dom.el( "p" , { class: "small " + ( state.why && !linked.length && state.url ? "text-warning-emphasis" : "text-body-secondary" ) , text: linkNote } ) );
      body.push(
        Dom.el( "h3" , { class: "h6 mt-3" , text: I18n.get( "lists.sheet_brings" ) } ),
        Dom.el( "div" , { class: "mb-2" , children: choices.length ? choices : [ Dom.el( "p" , { class: "small text-body-secondary" , text: I18n.get( "lists.sheet_no_columns" ) } ) ] } ),
        Dom.el( "p" , { class: "form-text" , text: I18n.get( "lists.sheet_over_help" ) } ),
        Dom.el( "h3" , { class: "h6 mt-3" , text: I18n.get( "lists.sheet_order" ) } ),
        radio( "list" , "lists.sheet_order_list" ),
        radio( "sheet" , "lists.sheet_order_sheet" , moves ? I18n.get( "lists.sheet_order_moves" ).replace( "{moves}" , moves ).replace( "{count}" , count ) : I18n.get( "lists.sheet_order_same" ) ),
      );
      const go = Dom.el( "button" , { class: "btn btn-primary" , attrs: { type: "button" } , text: I18n.get( "lists.sheet_import" ) , on: { click: apply } } );
      go.disabled = lists.view.locked;
      return { body: body , foot: [ go ] };
    } );
  },
};
