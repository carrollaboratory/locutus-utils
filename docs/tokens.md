# API Tokens

With the release of Map Dragon's backend v2.3, any interaction outside the
front-end will require an API token. These tokens are typically expected to be
managed through the front-end itself, but, for someone with direct access to the
database, they can also be managed via the command line.

_loctok_ Loctok is a set of utilities that are installed as part of
locutus-utils. These tools are designed to allow users the ability to manage API
tokens via the command line.

There are currently 3 tools:

- create
- list
- delete

At the time of writing, all of these require the email address for a user with
an active user account.

## create

Creating new API tokens is straightforward when using loctok.

```bash
$ loctok -db $MONGO_DEV create -e XYXYXYXYXY.XYXYXY@vumc.org -n "my API token"

                         User Details

  Setting                Value
 ─────────────────────────────────────────────────────────────
  TOKEN                  lct_XYXYXYXYXYXYXYXYXYXXYXYXYXY
  User ID                6aaae1102b1130616138961a
  Token Name             my API token
  Expires At             2027-09-17T11:23:23.188229

╭────────────────────────────────────────────────────────────────────────────────────╮
│                                                                                    │
│  ⚠️  IMPORTANT SECURITY WARNING                                                    │
│                                                                                    │
│  Make sure to copy your this token now. You will not be able to see it again.      │
│  You are responsible for safely storing this token (e.g., in a password manager).  │
│                                                                                    │
╰────────────────────────────────────────────────────────────────────────────────────╯

```

Similarly to the github personal access tokens, these tokens are not actually
stored in the database, so the response from the script itself is the last time
locutus or one of it's related tools will have access to it. As per standard
practice, this token should never get checked into version control, logged, or
made available to external users in any other way.

In addition to giving the token a name, the user can also provide an Expiration
Date via the argument --expiration-date.

## list

Users can review a list of tokens created for a specific user. This is helpful
if a user wishes to delete a token based on a particular token name:

```bash
$ loctok -db $MONGO_DEV list -e XYXYXYXYX.XYXYXY@vumc.org

                                 Token Details

  Token ID                         Token Name             Expires At
 ──────────────────────────────────────────────────────────────────────────────
  6aabfdb92584ef11193b1a87         my API token 1         2027-09-17T09:48:25…
  6aabfdc9899966cc1ba256c3         my API token 2         2027-09-17T09:48:41…
  6aabfdd9df107017af1757d3         my API token 3         2027-09-17T09:48:57…
  6aabfeb9a3e632421ecefd0e         my API token 4         2027-09-17T09:52:41…
  6aabff0b1196dc9bb58a83b5         my API token 5         2027-09-17T09:54:03…
  6aabff2002dde2d1fd215f28         my API token 6         2027-09-17T09:54:24…
```

## delete

Finally, users can delete one or more tokens for a given user:

```bash
$ loctok -db $MONGO_DEV delete -t 6aabfdb92584ef11193b1a87 -e XYXYXYXYX.XYXYXY@vumc.org
Database URI: mongodb://localhost:27017/alpha
Mongo DB URI: mongodb://localhost:27017/alpha
Are you sure you want to delete the specified token(s)? y/N: y
                                    Token Details

                                   Token
  Token ID                         Status       Token Name     Expires At
 ───────────────────────────────────────────────────────────────────────────────────
  6aabfdb92584ef11193b1a87         🟥           my API token 1 2027-09-17T09:48:25…
  6aabfdc9899966cc1ba256c3         ✅           my API token 2 2027-09-17T09:48:41…
  6aabfdd9df107017af1757d3         ✅           my API token 3 2027-09-17T09:48:57…
  6aabfeb9a3e632421ecefd0e         ✅           my API token 4 2027-09-17T09:52:41…
  6aabff0b1196dc9bb58a83b5         ✅           my API token 5 2027-09-17T09:54:03…
  6aabff2002dde2d1fd215f28         ✅           my API token 6 2027-09-17T09:54:24…
```

For this to continue, the user must confirm they wish to proceed, since it can't
be undone.

A table, not unlike the list, is provided showing which token(s) were deleted
and which remain. Users can provide multiple tokens at once, or they can use the
'all' standin for the token name.

```bash
$ loctok -db $MONGO_DEV delete -t all -e -e XYXYXYXYX.XYXYXY@vumc.org

Are you sure you want to delete the specified token(s)? y/N: y
                                    Token Details

                                   Token
  Token ID                         Status       Token Name     Expires At
 ───────────────────────────────────────────────────────────────────────────────────
  6aabfeb9a3e632421ecefd0e         🟥           my API token 4 2027-09-17T09:52:41…
  6aabff0b1196dc9bb58a83b5         🟥           my API token 5 2027-09-17T09:54:03…
  6aabff2002dde2d1fd215f28         🟥           my API token 6 2027-09-17T09:54:24…
```
