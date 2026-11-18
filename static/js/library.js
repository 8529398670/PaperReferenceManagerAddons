// How the Zotero library is doing: the live line on Info, and a warning on the
// Library screen (Lists) when Zotero could not be read.
//
// The papers themselves are the built-in Library list (#lists/library), drawn
// like any other list by lists.js. The server reads Zotero live and says so
// over /api/library/stream: "changed" when papers were added, changed or
// removed (lists.js fetches the Library list again), "progress" while full
// text is being made searchable (the status line moves on).
const Library = {
  async init() {
    await PaperLinks.init();
    Content.on( "changed" , () => this.refreshStatus() );
    Content.on( "progress" , () => this.refreshStatus() );
    await this.refreshStatus();
  },

  status( status ) {
    let text;
    if ( status.error ) text = I18n.get( "library.zotero_missing" ).replace( "{error}" , () => status.error );
    else if ( !status.ready ) text = I18n.get( "library.loading" );
    else if ( status.text_pending > 0 ) text = I18n.get( "library.indexing" ).replace( "{pending}" , status.text_pending.toLocaleString() );
    else {
      text = I18n.get( "library.ready" )
        .replace( "{with_text}" , ( status.with_text || 0 ).toLocaleString() )
        .replace( "{papers}" , ( status.papers || 0 ).toLocaleString() );
    }
    Dom.text( Dom.get( "library-status" ) , text );
    const problem = Dom.get( "library-problem" );
    Dom.text( problem , status.error ? text : "" );
    Dom.show( problem , Boolean( status.error ) );
  },

  async refreshStatus() {
    try {
      this.status( await Api.request( "/api/library/status" ) );
    } catch ( error ) { /* the next event tries again */ }
  },
};
