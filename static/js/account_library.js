// "Your library" on the Account screen: read your own ZoteroWebDAV server
// instead of this server's library, or go back to it. Browser sessions only,
// like two-factor. The stored key is never sent back: the key field is empty
// and says whether one is stored. See app/routes/account_library.py.
const AccountLibrary = {
  state: null,
  timer: 0,

  init( me ) {
    if ( me.auth !== "session" || !me.library ) return;
    Dom.show( Dom.get( "account-library-panel" ) , true );
    Dom.onSubmit( Dom.get( "account-library-form" ) , this.onSave.bind( this ) );
    Dom.get( "account-library-clear" ).addEventListener( "click" , this.onClear.bind( this ) );
    this.show( me.library , true );
  },

  // fill: also put the stored values in the fields (not while someone types).
  show( state , fill ) {
    this.state = state;
    const badge = Dom.get( "account-library-badge" );
    Dom.text( badge , I18n.get( state.own ? "account.library_own" : "account.library_server" ) );
    badge.className = "badge " + ( state.own ? "text-bg-primary" : "text-bg-secondary" );
    const status = Dom.get( "account-library-status" );
    status.className = "small mb-3 " + ( state.error ? "text-danger" : "text-body-secondary" );
    let line;
    if ( state.error ) {
      line = I18n.get( "account.library_status_error" ).replace( "{error}" , state.error );
    } else if ( !state.own ) {
      line = I18n.get( "account.library_status_server" ).replace( "{papers}" , String( state.papers ) );
    } else if ( !state.ready && !state.last_sync ) {
      line = I18n.get( "account.library_status_loading" );
    } else {
      line = I18n.get( "account.library_status_own" )
        .replace( "{papers}" , String( state.papers ) )
        .replace( "{when}" , state.last_sync ? Dom.ago( new Date( state.last_sync * 1000 ) ) : "-" );
    }
    Dom.text( status , line );
    const key = Dom.get( "account-library-key" );
    key.placeholder = I18n.get( state.key_set ? "account.library_key_placeholder_set" : "account.library_key_placeholder_new" );
    key.required = !state.key_set;
    Dom.show( Dom.get( "account-library-clear" ) , state.own );
    if ( fill ) {
      Dom.get( "account-library-url" ).value = state.url;
      Dom.get( "account-library-name" ).value = state.name;
      key.value = "";
    }
    this.follow();
  },

  // While a library is being read for the first time, look again now and
  // then, so the count appears without a reload.
  follow() {
    window.clearTimeout( this.timer );
    if ( !this.state || !this.state.own || this.state.error || ( this.state.ready && this.state.last_sync ) ) return;
    this.timer = window.setTimeout( async () => {
      try {
        const me = await Api.request( "/api/me" );
        this.show( me.library , false );
      } catch ( error ) {
        // Quiet: the next look, or a reload, says more.
      }
    } , 5000 );
  },

  async onSave( event ) {
    event.preventDefault();
    const button = Dom.get( "account-library-save" );
    button.disabled = true;
    try {
      const state = await Api.post( "/api/account/library" , {
        url: Dom.get( "account-library-url" ).value.trim(),
        key: Dom.get( "account-library-key" ).value.trim(),
        library: Dom.get( "account-library-name" ).value.trim(),
      } );
      this.show( state , true );
      Dom.toast( I18n.get( "account.library_saved" ) , "ok" );
    } catch ( error ) {
      Dom.fieldError( Dom.get( "account-library-url" ) , Dom.worded( error ) );
    } finally {
      button.disabled = false;
    }
  },

  async onClear() {
    if ( !( await Dom.confirm( I18n.get( "account.library_clear_confirm" ) ) ) ) return;
    try {
      const state = await Api.post( "/api/account/library/clear" , {} );
      this.show( state , true );
      Dom.toast( I18n.get( "account.library_cleared" ) , "ok" );
    } catch ( error ) {
      App.showError( Dom.worded( error ) );
    }
  },
};
