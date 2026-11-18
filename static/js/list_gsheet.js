// A list's Google Sheet mirror (app/boards/sheetsync.py), from the list menu:
// off, one-way (the list is pushed to its sheet a few seconds after each
// change) or two-way (the sheet is also read back, and what was typed there
// becomes edits to the list, by "Google Sheet", in its history). The first
// switch on makes the spreadsheet. Sync now, Open sheet, and Overwrite the
// sheet (the list written over whatever was typed there since the last read).
const ListGSheet = {
  slug: "",
  sheet: null,
  timer: null,

  init() {
    Dom.all( "input[name=gsheet-mode]" ).forEach( ( radio ) => radio.addEventListener( "change" , () => this.set( { mode: radio.value } ) ) );
    Dom.onPress( Dom.get( "gsheet-sync" ) , () => this.set( { sync_now: true } ) );
    Dom.onPress( Dom.get( "gsheet-overwrite" ) , async () => {
      if ( !await Dom.confirm( I18n.get( "gsheet.overwrite_confirm" ) ) ) return;
      await this.set( { overwrite: true } );
    } );
    Dom.get( "gsheet-dialog" ).addEventListener( "hidden.bs.modal" , () => {
      clearInterval( this.timer );
      this.timer = null;
    } );
  },

  async open( slug ) {
    if ( !this.ready ) {
      this.init();
      this.ready = true;
    }
    this.slug = slug;
    try {
      this.sheet = ( await Api.request( "/api/lists/" + encodeURIComponent( slug ) + "/sheet" ) ).sheet;
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      return;
    }
    this.draw();
    bootstrap.Modal.getOrCreateInstance( Dom.get( "gsheet-dialog" ) ).show();
    // While open, what the worker did shows up (a push takes a few seconds).
    clearInterval( this.timer );
    this.timer = setInterval( () => this.refresh() , 4000 );
  },

  async refresh() {
    try {
      this.sheet = ( await Api.request( "/api/lists/" + encodeURIComponent( this.slug ) + "/sheet" ) ).sheet;
      this.draw();
    } catch ( error ) { /* shown on the next press */ }
  },

  async set( change ) {
    try {
      this.sheet = ( await Api.post( "/api/lists/" + encodeURIComponent( this.slug ) + "/sheet" , change ) ).sheet;
    } catch ( error ) {
      Dom.toast( error.message , "error" );
      this.draw();
      return;
    }
    this.draw();
    if ( change.sync_now || change.overwrite ) Dom.toast( I18n.get( "gsheet.syncing" ) , "success" );
  },

  draw() {
    const sheet = this.sheet || {};
    const on = sheet.mode && sheet.mode !== "off";
    Dom.show( Dom.get( "gsheet-unavailable" ) , !sheet.available );
    Dom.all( "input[name=gsheet-mode]" ).forEach( ( radio ) => {
      radio.checked = radio.value === ( sheet.mode || "off" );
      radio.disabled = !sheet.available && radio.value !== "off";
    } );
    const when = ( value ) => ( value ? new Date( value ).toLocaleString() : I18n.get( "gsheet.never" ) );
    Dom.text( Dom.get( "gsheet-last-push" ) , when( sheet.last_push ) + ( sheet.pending ? " · " + I18n.get( "gsheet.pending" ) : "" ) );
    Dom.text( Dom.get( "gsheet-last-pull" ) , sheet.mode === "two-way" ? when( sheet.last_pull ) : I18n.get( "gsheet.not_two_way" ) );
    Dom.text( Dom.get( "gsheet-error" ) , sheet.error || "" );
    Dom.show( Dom.get( "gsheet-error" ) , Boolean( sheet.error ) );
    Dom.text( Dom.get( "gsheet-note" ) , sheet.note || "" );
    Dom.show( Dom.get( "gsheet-note" ) , Boolean( sheet.note ) );
    const open = Dom.get( "gsheet-open" );
    Dom.show( open , Boolean( sheet.url ) );
    if ( sheet.url ) open.setAttribute( "href" , sheet.url );
    Dom.show( Dom.get( "gsheet-sync" ) , on && sheet.available );
    Dom.show( Dom.get( "gsheet-overwrite" ) , on && sheet.available && Boolean( sheet.spreadsheet_id ) );
  },
};
