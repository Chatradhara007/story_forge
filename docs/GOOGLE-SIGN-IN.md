# Google sign-in ("Continue with Google")

Email-and-password accounts work without this. Google sign-in is an extra button on the
sign-in and create-account screens; it only appears when `GOOGLE_CLIENT_ID` is set.

## Set it up (about 10 minutes, free)

1. Go to https://console.cloud.google.com, create a project (e.g. "StoryForge").
2. **APIs & Services → OAuth consent screen**: choose *External*, fill in the app name,
   support email and developer email. While it is in *Testing*, add the Google accounts that
   may sign in under **Test users** (fine for a pitch); publish it later for everyone.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - **Authorised JavaScript origins**: every address the website is opened from, e.g.
     `http://localhost:8000`, `http://127.0.0.1:8000`, and later `https://your-site.onrender.com`.
     No redirect URIs are needed.
4. Copy the **Client ID** (ends in `.apps.googleusercontent.com`) into `backend/.env`:
   ```
   AUTH_REQUIRED=true
   SECRET_KEY=<long random text: python -c "import secrets; print(secrets.token_hex(32))">
   GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
   ```
   No client secret is needed: the server checks each sign-in with Google directly.
5. Restart the backend. The sign-in screen now shows **Continue with Google**.

## How it behaves

- First Google sign-in with an email that has no account: a new account is made (same rules as
  registering: registration must be open, and the invite code is asked for if one is set).
- An existing account with the same email: signs into that account (Google has verified the email).
- A Google-made account has no password; "Forgot your password?" sets one if wanted.
- The server accepts only credentials made for this client ID, from Google, with a verified email.
