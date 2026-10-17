# Setting up Song for Song

The app works right away in **demo mode** with sample songs. Follow these steps to put it on the web
and connect real Spotify and Apple Music accounts. You only do this once.

## 1. Put the app on the web (free, about 2 minutes)

1. Go to https://github.com/Jelani2322/my-first-project
2. Click **Settings** (top of the page), then **Pages** (left side).
3. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
4. Under **Branch**, pick `claude/music-battle-tournament-c24qrh` and `/ (root)`, then click **Save**.
5. Wait 1–2 minutes. Your app will be live at **https://jelani2322.github.io/my-first-project/**

Song previews for the crowd work as soon as the site is live. They need no keys.

## 2. Connect Spotify (free)

1. Go to https://developer.spotify.com/dashboard and log in with your Spotify account.
2. Click **Create app**.
   - App name: `Song for Song`
   - App description: `Music battle tournament`
   - Redirect URI: `https://jelani2322.github.io/my-first-project/` (click **Add**)
   - Under "Which API/SDKs are you planning to use?", check **Web API**.
   - Agree to the terms and click **Save**.
3. Open the app's **Settings** and copy the **Client ID**.
4. On GitHub, open `config.js`, click the pencil icon to edit, and paste the Client ID between the quotes:
   `spotifyClientId: "paste-it-here",`
   Then click **Commit changes**.

**Important:** new Spotify apps start in development mode. Only the Spotify accounts you add under
**User Management** in your app's settings can link. Add each player's name and Spotify email there.
To open it to everyone, Spotify has to approve your app, and they have strict requirements.

## 3. Connect Apple Music (costs $99/year)

Apple requires a paid **Apple Developer Program** membership to connect to Apple Music.
Players who link Apple Music also need an Apple Music subscription.

1. Join at https://developer.apple.com/programs/
2. In **Certificates, Identifiers & Profiles**:
   - Under **Identifiers**, create a **Media ID** with MusicKit turned on.
   - Under **Keys**, create a key with **Media Services (MusicKit)** turned on and download the `.p8` file.
     Keep this file private. Never upload it to GitHub.
3. The `.p8` key is used to make a **developer token** that lasts up to 6 months.
   Ask Claude to walk you through making one, then paste the token into `config.js`:
   `appleDeveloperToken: "paste-it-here",`

## How playing works

- **Linking:** each player taps Link Spotify or Link Apple Music and signs in. The app copies their
  Liked Songs / library and playlists (up to about 2,000 songs) and then lets go of the account.
  On a shared device, Spotify shows a "Not you?" link so the next player can switch accounts.
- **Genre:** chosen before the tournament. Songs show their genre, and a gold tag warns when a
  song is outside the genre. The crowd decides whether it counts.
- **Topics:** each round gets a random topic, like "A song about money". Players search their own
  songs to find one that fits.
- **Listening:** tap Play song on each side. The 30-second clip plays from the device, so connect
  it to a speaker or TV for the crowd.
- **Voting:** everyone taps once for the song that fits the topic best. Lock in the winner.
  First to 2 round wins advances.
