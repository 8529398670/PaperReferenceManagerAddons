// "Your library" on the Account screen: choose this server's library or your
// own ZoteroWebDAV server, and which of that server's WebDAV libraries to
// read (a dropdown filled from it). Browser sessions only, like two-factor.
// The stored key is never sent back: the key field is empty and says whether
// one is stored, and the list is fetched with the stored key when it is left
// empty. See app/routes/account_library.py.
const AccountLibrary = {
  state: null,
  timer: 0,
  // The address and key the dropdown was last filled for.
  listedFor: "",

  init( me ) {
    if ( me.auth !== "session" || !me.library ) return;
    Dom.show( Dom.get( "account-library-panel" ) , true );
    Dom.onSubmit( Dom.get( "account-library-form" ) , this.onSave.bind( this ) );
    for ( const radio of document.querySelectorAll( "input[name='account-library-choice']" ) ) {
      radio.addEventListener( "change" , this.onChoice.bind( this ) );
    }
    Dom.get( "account-library-load" ).addEventListener( "click" , () => this.loadLibraries( true ) );
    for ( const id of [ "account-library-url" , "account-library-key" ] ) {
      Dom.get( id ).addEventListener( "change" , () => this.loadLibraries( false ) );
    }
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
    if ( fill ) {
      Dom.get( state.own ? "account-library-choice-own" : "account-library-choice-server" ).checked = true;
      Dom.show( Dom.get( "account-library-form" ) , state.own );
      Dom.get( "account-library-url" ).value = state.url;
      key.value = "";
      this.listedFor = "";
      this.setOptions( [] , state.name );
      if ( state.own ) this.loadLibraries( false );
    }
    this.follow();
  },

  // The dropdown: the server's libraries, the chosen one selected (an empty
  // name is the default one). With none listed, one "default" choice, so the
  // form still saves.
  setOptions( rows , chosen ) {
    const select = Dom.get( "account-library-name" );
    select.replaceChildren();
    if ( rows.length === 0 ) {
      select.append( Dom.el( "option" , { text: chosen || I18n.get( "account.library_name_default_option" ) , attrs: { value: chosen || "" } } ) );
      return;
    }
    for ( const row of rows ) {
      let text = row.primary ? I18n.get( "account.library_name_primary" ).replace( "{name}" , row.name ) : row.name;
      if ( row.label ) text += " - " + row.label;
      const option = Dom.el( "option" , { text: text , attrs: { value: row.primary ? "" : row.name } } );
      if ( chosen ? chosen === row.name : row.primary ) option.selected = true;
      select.append( option );
    }
  },

  // force: list again even for the same address and key (the button).
  async loadLibraries( force ) {
    const url = Dom.get( "account-library-url" ).value.trim();
    const key = Dom.get( "account-library-key" ).value.trim();
    const select = Dom.get( "account-library-name" );
    if ( !url || ( !key && !( this.state && this.state.key_set ) ) ) return;
    const asked = url + "\n" + key;
    if ( !force && asked === this.listedFor ) return;
    this.listedFor = asked;
    const chosen = select.value || ( this.state && this.state.own ? this.state.name : "" );
    const button = Dom.get( "account-library-load" );
    button.disabled = true;
    Dom.clearFieldError( select );
    try {
      const reply = await Api.post( "/api/account/library/libraries" , { url: url , key: key } );
      if ( asked !== this.listedFor ) return;
      this.setOptions( reply.libraries , chosen );
    } catch ( error ) {
      if ( asked !== this.listedFor ) return;
      this.listedFor = "";
      this.setOptions( [] , chosen );
      Dom.fieldError( select , I18n.get( "account.library_name_load_error" ).replace( "{error}" , Dom.worded( error ) ) );
    } finally {
      button.disabled = false;
    }
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

  async onChoice( event ) {
    const own = event.target.value === "own";
    if ( own ) {
      Dom.show( Dom.get( "account-library-form" ) , true );
      this.loadLibraries( false );
      return;
    }
    if ( !this.state.own ) {
      Dom.show( Dom.get( "account-library-form" ) , false );
      return;
    }
    if ( !( await Dom.confirm( I18n.get( "account.library_clear_confirm" ) ) ) ) {
      Dom.get( "account-library-choice-own" ).checked = true;
      return;
    }
    try {
      const state = await Api.post( "/api/account/library/clear" , {} );
      this.show( state , true );
      Dom.toast( I18n.get( "account.library_cleared" ) , "ok" );
    } catch ( error ) {
      Dom.get( "account-library-choice-own" ).checked = true;
      App.showError( Dom.worded( error ) );
    }
  },

  async onSave( event ) {
    event.preventDefault();
    const button = Dom.get( "account-library-save" );
    button.disabled = true;
    try {
      const state = await Api.post( "/api/account/library" , {
        url: Dom.get( "account-library-url" ).value.trim(),
        key: Dom.get( "account-library-key" ).value.trim(),
        library: Dom.get( "account-library-name" ).value,
      } );
      this.show( state , true );
      Dom.toast( I18n.get( "account.library_saved" ) , "ok" );
    } catch ( error ) {
      Dom.fieldError( Dom.get( "account-library-url" ) , Dom.worded( error ) );
    } finally {
      button.disabled = false;
    }
  },
};
