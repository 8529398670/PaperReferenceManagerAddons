// The server's live streams (server-sent events), shared by every tab.
//
// A browser keeps at most six connections open to one server over plain
// HTTP/1.1, and each stream holds one open for as long as the page is open.
// With a stream or two per tab, three tabs used them all up, and every other
// request (a search, a save) waited forever for a free one: buttons just spun.
// So only one tab -- the leader, whoever holds the "prma-live" lock -- opens
// the streams, and it passes every event on to the other tabs over a
// BroadcastChannel. When the leader closes, the lock goes to another tab,
// which opens the streams in its place; the other tabs then say again which
// streams they want.
//
// A leader can also stop without closing: a page put in the back-forward
// cache, or frozen by the browser in the background, still holds the lock but
// relays nothing. So a leader lets go of the lock (and its streams) when the
// page is hidden away like that, and says it is alive every few seconds; a
// tab in front that has heard nothing for a while takes the lock from it.
//
// The server holds the same line: it answers an older page's stream with 204
// (no reconnecting), and a second stream from one session replaces the first
// ("replaced"), so no mix of tabs can use up the connections again.
//
// Live.on( url , name , handler ) hears event `name` on stream `url`; the
// handler gets { data } like an EventSource event. Without the lock or the
// channel (an old browser, or a plain-http address that is not this machine)
// each tab opens its own streams, as before.
const Live = {
  lockName: "prma-live",
  shared: typeof BroadcastChannel !== "undefined" && !!( navigator.locks && navigator.locks.request ),
  // How often the leader says it is alive, and how long a tab in front waits
  // without hearing it before taking over. Generous: a leader in a background
  // tab has its timers slowed by the browser.
  beatMs: 5000,
  staleMs: 20000,
  channel: null,
  leader: false,
  heardAt: 0,
  // Lets go of the lock (leader), or drops the request for it (waiting).
  release: null,
  waiting: null,
  timer: 0,
  // url -> Set of event names this tab listens for.
  wanted: {},
  // url -> event name -> [handlers] in this tab.
  handlers: {},
  // Leader only: url -> EventSource, and url -> Set of names listened on it.
  sources: {},
  listening: {},

  on( url , name , handler ) {
    if ( typeof EventSource === "undefined" ) return;
    this.handlers[ url ] = this.handlers[ url ] || {};
    ( this.handlers[ url ][ name ] = this.handlers[ url ][ name ] || [] ).push( handler );
    ( this.wanted[ url ] = this.wanted[ url ] || new Set() ).add( name );
    if ( !this.shared ) {
      this.listen( url , name );
      return;
    }
    this.start();
    if ( this.leader ) this.listen( url , name );
    else this.channel.postMessage( { type: "want" , url: url , names: [ name ] } );
  },

  start() {
    if ( this.channel ) return;
    this.channel = new BroadcastChannel( this.lockName );
    this.channel.onmessage = ( message ) => this.heard( message.data || {} );
    this.heardAt = Date.now();
    this.claim( false );
    // Whoever leads now hears what this tab wants.
    this.announce();
    // Hidden away (back-forward cache, frozen): a page that relays nothing
    // must not keep the lock. Back again: ask for it like any other tab.
    window.addEventListener( "pagehide" , () => this.stepDown() );
    document.addEventListener( "freeze" , () => this.stepDown() );
    window.addEventListener( "pageshow" , ( event ) => {
      if ( event.persisted ) this.comeBack();
    } );
    document.addEventListener( "resume" , () => this.comeBack() );
    document.addEventListener( "visibilitychange" , () => this.check() );
    this.timer = window.setInterval( () => this.tick() , this.beatMs );
  },

  // Asks for the lock and leads while it is held. steal: take it from a
  // leader that has gone quiet.
  claim( steal ) {
    if ( this.waiting ) this.waiting.abort();
    const options = {};
    let waiting = null;
    if ( steal ) {
      options.steal = true;
    } else if ( typeof AbortController !== "undefined" ) {
      waiting = new AbortController();
      options.signal = waiting.signal;
    }
    this.waiting = waiting;
    navigator.locks.request( this.lockName , options , () => {
      if ( this.waiting === waiting ) this.waiting = null;
      // Held until this tab goes away or steps down.
      return new Promise( ( resolve ) => {
        this.release = resolve;
        this.lead();
      } );
    } ).catch( () => {
      // Aborted while waiting, or taken by another tab (steal): not leading.
      if ( this.leader ) this.follow();
    } );
  },

  lead() {
    this.leader = true;
    Object.keys( this.wanted ).forEach( ( url ) => this.wanted[ url ].forEach( ( name ) => this.listen( url , name ) ) );
    // Every other tab says again what it wants, since the old leader is gone.
    this.channel.postMessage( { type: "hello" } );
  },

  // No longer the leader: close the streams, keep the handlers.
  follow() {
    this.leader = false;
    this.release = null;
    Object.values( this.sources ).forEach( ( source ) => source.close() );
    this.sources = {};
    this.listening = {};
    this.heardAt = Date.now();
  },

  stepDown() {
    if ( this.waiting ) {
      this.waiting.abort();
      this.waiting = null;
    }
    if ( !this.leader ) return;
    const release = this.release;
    this.follow();
    if ( release ) release();
  },

  comeBack() {
    if ( !this.channel || this.leader ) return;
    this.heardAt = Date.now();
    this.claim( false );
    this.announce();
  },

  tick() {
    if ( this.leader ) this.channel.postMessage( { type: "beat" } );
    else this.check();
  },

  // A tab in front that has not heard the leader for a while takes over.
  check() {
    if ( this.leader || !this.channel || document.hidden ) return;
    if ( Date.now() - this.heardAt < this.staleMs ) return;
    this.heardAt = Date.now();
    this.claim( true );
  },

  announce() {
    Object.keys( this.wanted ).forEach( ( url ) => {
      this.channel.postMessage( { type: "want" , url: url , names: Array.from( this.wanted[ url ] ) } );
    } );
  },

  heard( message ) {
    if ( message.type === "event" || message.type === "beat" || message.type === "hello" ) this.heardAt = Date.now();
    if ( message.type === "event" ) {
      this.deliver( message.url , message.name , message.data );
    } else if ( message.type === "want" && this.leader ) {
      ( message.names || [] ).forEach( ( name ) => this.listen( message.url , name ) );
    } else if ( message.type === "hello" && !this.leader ) {
      this.announce();
    }
  },

  // Opens the stream if it is not open yet, and listens for one more event name.
  listen( url , name ) {
    if ( typeof url !== "string" || !url.startsWith( "/api/" ) ) return;
    if ( !this.sources[ url ] ) {
      // v=2: this protocol (the server refuses older pages' streams). solo:
      // this tab cannot share, so the server must not count it as the
      // session's one stream.
      const source = new EventSource( url + "?v=2" + ( this.shared ? "" : "&solo=1" ) );
      this.sources[ url ] = source;
      this.listening[ url ] = new Set();
      // The server ended it because a newer stream of this session took its
      // place: another tab leads now. Stop, and do not reconnect.
      source.addEventListener( "replaced" , () => {
        source.close();
        if ( this.sources[ url ] !== source ) return;
        if ( this.shared && this.leader ) this.stepDown();
        else {
          delete this.sources[ url ];
          delete this.listening[ url ];
        }
      } );
    }
    if ( this.listening[ url ].has( name ) ) return;
    this.listening[ url ].add( name );
    const source = this.sources[ url ];
    source.addEventListener( name , ( event ) => {
      // A stream closed on stepping down can still hand over one last event.
      if ( this.shared && this.sources[ url ] !== source ) return;
      this.deliver( url , name , event.data );
      if ( this.shared ) this.channel.postMessage( { type: "event" , url: url , name: name , data: event.data } );
    } );
  },

  deliver( url , name , data ) {
    const handlers = ( this.handlers[ url ] || {} )[ name ] || [];
    handlers.forEach( ( fn ) => fn( { data: data } ) );
  },
};
