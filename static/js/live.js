// The server's live streams (server-sent events), shared by every tab.
//
// A browser keeps at most six connections open to one server over plain
// HTTP/1.1, and each stream holds one open for as long as the page is open.
// With a stream or two per tab, three tabs used them all up, and the next tab
// or refresh waited forever for a free one. So only one tab -- the leader,
// whoever holds the "prma-live" lock -- opens the streams, and it passes every
// event on to the other tabs over a BroadcastChannel. When the leader closes,
// the lock goes to another tab, which opens the streams in its place; the
// other tabs then say again which streams they want.
//
// Live.on( url , name , handler ) hears event `name` on stream `url`; the
// handler gets { data } like an EventSource event. Without the lock or the
// channel (an old browser, or a plain-http address that is not this machine)
// each tab opens its own streams, as before.
const Live = {
  lockName: "prma-live",
  shared: typeof BroadcastChannel !== "undefined" && !!( navigator.locks && navigator.locks.request ),
  channel: null,
  leader: false,
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
    // Held until this tab goes away; the promise never settles on purpose.
    navigator.locks.request( this.lockName , () => new Promise( () => this.lead() ) ).catch( () => {} );
    // Whoever leads now hears what this tab wants.
    this.announce();
  },

  lead() {
    this.leader = true;
    Object.keys( this.wanted ).forEach( ( url ) => this.wanted[ url ].forEach( ( name ) => this.listen( url , name ) ) );
    // Every other tab says again what it wants, since the old leader is gone.
    this.channel.postMessage( { type: "hello" } );
  },

  announce() {
    Object.keys( this.wanted ).forEach( ( url ) => {
      this.channel.postMessage( { type: "want" , url: url , names: Array.from( this.wanted[ url ] ) } );
    } );
  },

  heard( message ) {
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
      this.sources[ url ] = new EventSource( url );
      this.listening[ url ] = new Set();
    }
    if ( this.listening[ url ].has( name ) ) return;
    this.listening[ url ].add( name );
    this.sources[ url ].addEventListener( name , ( event ) => {
      this.deliver( url , name , event.data );
      if ( this.shared ) this.channel.postMessage( { type: "event" , url: url , name: name , data: event.data } );
    } );
  },

  deliver( url , name , data ) {
    const handlers = ( this.handlers[ url ] || {} )[ name ] || [];
    handlers.forEach( ( fn ) => fn( { data: data } ) );
  },
};
