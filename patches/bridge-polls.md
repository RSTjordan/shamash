# Patch: native polls (send, vote decryption, test vote endpoint)

Adds WhatsApp-native poll support to the bridge. Three pieces: a
`POST /api/poll` endpoint (send a poll), decryption of incoming poll
votes into `messages.db`, and a `POST /api/vote` loopback endpoint that
lets this account vote on a poll it has seen — the piece that makes
poll round-trips testable without a human tapping a phone.

Everything below goes into `whatsapp-bridge/main.go`. Function and line
anchors are descriptive, not positional — find them by name; the
upstream file drifts.

## Why votes need a hash table

WhatsApp encrypts poll votes with the poll message's key, and a
decrypted vote identifies its options only as SHA-256 hashes of the
option-label bytes. So the bridge must remember, per poll it sends,
the option→hash map — that is the `polls` table. Whoever truncates a
label must truncate before hashing; the bridge hashes exactly the
bytes it receives in the request.

## Who enforces WhatsApp's limits

Split deliberately, and the split is what keeps the hashes matching:

- **The kit truncates, before the POST.** `scripts/ask.py` cuts the
  question to **255** chars and every option to **100**, and if two
  labels collide after that cut it renumbers them all (`1) …`, `2) …`)
  — two identical labels hash identically and a vote for either would
  be indistinguishable. It also clamps `selectable_count` into
  `[1, len(options)]`.
- **The bridge validates, and rejects.** The handler below 400s a
  request with no recipient, no question, or fewer than 1 / more than
  **12** options. It truncates nothing: silently shortening a label
  here would hash bytes the caller never chose, and the caller's own
  equality checks against its option list would then fail.

So a caller that hand-rolls a poll POST can be rejected outright; the
kit's own path never hits the limits, because it has already cut.

The whatsmeow API used (quote of the vendored signatures — verify they
match your clone's vendored `go.mau.fi/whatsmeow/msgsecret.go` before
building, and adapt if the upstream signature drifted):

```go
func (cli *Client) BuildPollCreation(name string, optionNames []string,
        selectableOptionCount int) *waE2E.Message
func (cli *Client) DecryptPollVote(ctx context.Context,
        vote *events.Message) (*waE2E.PollVoteMessage, error)
func (cli *Client) BuildPollVote(ctx context.Context,
        pollInfo *types.MessageInfo, optionNames []string) (*waE2E.Message, error)
func HashPollOptions(optionNames []string) [][]byte  // package-level helper
```

Imports: sections 3 and 5 below both need `"encoding/hex"` added to
main.go's import block (it is not there today). Section 3 uses
`whatsmeow.HashPollOptions` for hashing — the same function whatsmeow
uses internally, so the stored hashes match incoming votes by
construction and no `crypto/sha256` import is needed.

## 1. The `polls` table

In the `MessageStore` initializer, next to the existing
`CREATE TABLE IF NOT EXISTS messages` statement, add:

```go
_, err = db.Exec(`CREATE TABLE IF NOT EXISTS polls (
    message_id TEXT,
    chat_jid TEXT,
    option_name TEXT,
    option_hash TEXT,
    PRIMARY KEY (message_id, chat_jid, option_hash)
)`)
if err != nil {
    return nil, fmt.Errorf("failed to create polls table: %w", err)
}
```

## 2. Request/response types

Next to `SendMessageRequest` (search for `type SendMessageRequest`):

```go
// SendPollRequest is the body for POST /api/poll.
type SendPollRequest struct {
    Recipient       string   `json:"recipient"`
    Question        string   `json:"question"`
    Options         []string `json:"options"`
    SelectableCount int      `json:"selectable_count"`
}

// SendPollResponse mirrors SendMessageResponse but ALSO returns the
// message id — a deliberate new convention: the id is what the caller
// waits on for votes.
type SendPollResponse struct {
    Success   bool   `json:"success"`
    Message   string `json:"message"`
    MessageID string `json:"message_id,omitempty"`
}

// VoteRequest is the body for POST /api/vote — a TESTING endpoint:
// votes as this account on a poll this account has seen (whatsmeow
// needs the poll's message secret, which it stores when it sends or
// receives the poll). Loopback + bearer auth like everything else.
type VoteRequest struct {
    Recipient  string   `json:"recipient"`       // chat JID holding the poll (phone form)
    PollID     string   `json:"poll_id"`         // the poll's message id
    PollSender string   `json:"poll_sender_jid"` // full JID of the poll's sender — LID form
                                                 // for cross-account votes, see "The LID
                                                 // rule" below; phone form fails the MAC
    PollFromMe bool     `json:"poll_from_me"`    // whether this account sent the poll
    Options    []string `json:"options"`         // option labels to select (empty = clear vote)
}
```

## 3. `POST /api/poll` handler

In `newRESTMux`, after the `/api/send` handler, add:

```go
// Handler for sending native polls. Returns the message id (new
// convention vs /api/send) because vote-waiting keys on it.
mux.HandleFunc("/api/poll", auth(func(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }
    var req SendPollRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Invalid request format", http.StatusBadRequest)
        return
    }
    if req.Recipient == "" || req.Question == "" ||
        len(req.Options) < 1 || len(req.Options) > 12 {
        http.Error(w, "recipient, question and 1-12 options are required",
            http.StatusBadRequest)
        return
    }
    var recipientJID types.JID
    var err error
    if strings.Contains(req.Recipient, "@") {
        recipientJID, err = types.ParseJID(req.Recipient)
    } else {
        recipientJID = types.JID{User: req.Recipient, Server: "s.whatsapp.net"}
    }
    if err != nil {
        http.Error(w, fmt.Sprintf("Error parsing JID: %v", err), http.StatusBadRequest)
        return
    }
    sc := req.SelectableCount
    if sc < 1 || sc > len(req.Options) {
        sc = 1 // whatsmeow coerces bad values to 0 = unlimited; never allow that
    }
    pollMsg := client.BuildPollCreation(req.Question, req.Options, sc)
    resp, err := client.SendMessage(context.Background(), recipientJID, pollMsg)
    w.Header().Set("Content-Type", "application/json")
    if err != nil {
        w.WriteHeader(http.StatusInternalServerError)
        _ = json.NewEncoder(w).Encode(SendPollResponse{
            Success: false, Message: fmt.Sprintf("send failed: %v", err)})
        return
    }
    // Remember option hashes so incoming votes can be resolved to labels.
    // HashPollOptions is whatsmeow's own hashing — matching by construction.
    chatJID := recipientJID.String()
    hashes := whatsmeow.HashPollOptions(req.Options)
    for i, opt := range req.Options {
        if _, dbErr := messageStore.db.Exec(
            "INSERT OR IGNORE INTO polls (message_id, chat_jid, option_name, option_hash) VALUES (?, ?, ?, ?)",
            resp.ID, chatJID, opt, hex.EncodeToString(hashes[i]),
        ); dbErr != nil {
            fmt.Printf("failed to store poll option hash: %v\n", dbErr)
        }
    }
    // The poll's own row in messages.db — delivery verification reads it.
    // Guard the device ID like every other Store.ID site in this file: a
    // poll POST during a re-pair must not panic the bridge.
    sender := ""
    if client.Store.ID != nil {
        sender = client.Store.ID.User
    }
    if err := messageStore.StoreMessage(
        resp.ID, chatJID, sender, req.Question, resp.Timestamp, true,
        "poll", "", "", nil, nil, nil, 0, "",
    ); err != nil {
        fmt.Printf("failed to store poll row: %v\n", err)
    }
    _ = json.NewEncoder(w).Encode(SendPollResponse{
        Success: true, MessageID: resp.ID})
}))
```

(Imports were covered at the top of this doc: `"encoding/hex"` only.)

## 4. `POST /api/vote` handler (testing endpoint)

Directly after the `/api/poll` handler:

```go
// TESTING endpoint: cast this account's vote on a poll it has seen.
// Exists so poll round-trips are verifiable end-to-end without a human
// tapping a phone. Same auth story as every other endpoint (bearer
// token + loopback-only Host allow-list).
mux.HandleFunc("/api/vote", auth(func(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }
    var req VoteRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Invalid request format", http.StatusBadRequest)
        return
    }
    if req.Recipient == "" || req.PollID == "" || req.PollSender == "" {
        http.Error(w, "recipient, poll_id and poll_sender_jid are required",
            http.StatusBadRequest)
        return
    }
    chatJID, err := types.ParseJID(req.Recipient)
    if err != nil {
        http.Error(w, fmt.Sprintf("Error parsing chat JID: %v", err), http.StatusBadRequest)
        return
    }
    senderJID, err := types.ParseJID(req.PollSender)
    if err != nil {
        http.Error(w, fmt.Sprintf("Error parsing sender JID: %v", err), http.StatusBadRequest)
        return
    }
    pollInfo := types.MessageInfo{
        MessageSource: types.MessageSource{
            Chat: chatJID, Sender: senderJID, IsFromMe: req.PollFromMe,
            // Required: getKeyFromInfo only fills the key's Participant
            // when IsGroup is set, and without a participant the receiver
            // cannot attribute a group poll's vote.
            IsGroup: chatJID.Server == types.GroupServer,
        },
        ID: req.PollID,
    }
    voteMsg, err := client.BuildPollVote(context.Background(), &pollInfo, req.Options)
    w.Header().Set("Content-Type", "application/json")
    if err != nil {
        w.WriteHeader(http.StatusInternalServerError)
        _ = json.NewEncoder(w).Encode(SendMessageResponse{
            Success: false, Message: fmt.Sprintf("build vote failed: %v", err)})
        return
    }
    if _, err := client.SendMessage(context.Background(), chatJID, voteMsg); err != nil {
        w.WriteHeader(http.StatusInternalServerError)
        _ = json.NewEncoder(w).Encode(SendMessageResponse{
            Success: false, Message: fmt.Sprintf("send vote failed: %v", err)})
        return
    }
    _ = json.NewEncoder(w).Encode(SendMessageResponse{Success: true})
}))
```

### The LID rule (cross-account votes)

A vote cast on behalf of one account against a poll created by *another*
account MUST pass `poll_sender_jid` in **LID** form. Phone form silently
produces an undecryptable vote: the sender still gets `{"success":true}`,
and only the receiving bridge notices, with

```
cipher: message authentication failed
```

Section 5 handles a failed decryption with `logger.Warnf` and a bare
`return`, so nothing is ever written to `messages.db` and a caller waiting
on the vote just times out — that log line on the *receiving* bridge is
the only place the real error appears, and the first place to look.

The cause is in whatsmeow's `EncryptPollVote`:

```go
ownID := cli.getOwnLID()
if pollInfo.Sender.Server == types.DefaultUserServer {
    ownID = cli.getOwnID()   // phone JID
}
```

A phone-form sender flips whatsmeow into encrypting under the voter's
*phone* identity, while the receiving bridge derives the key from
`msg.Info.Sender`, which is the voter's **LID**. `generateMsgSecretKey`
mixes that identity into both the HKDF info and the GCM additional data,
so the MAC fails. whatsmeow's own retry hack only retries the *orig
sender* variant, never the *voter* variant, so it cannot recover.

Source the LID from the **voting** bridge's own `store\whatsapp.db`:

```sql
SELECT lid FROM whatsmeow_lid_map WHERE pn = ?;   -- pn = digits, no @suffix
```

and send it as `<lid>@lid`. `recipient` stays the **phone-form** chat JID —
the asymmetry is deliberate: `recipient` is both the send target and the
key used to look up the stored message secret, and both are keyed by the
phone-form chat.

This affects `/api/vote` only. A human tapping a poll on their phone is
unaffected — WhatsApp's own client already encrypts under the correct
identity.

## 5. Incoming vote decryption

In `handleMessage`, BEFORE the reaction block (search for
"Reactions arrive as their own message stanza"), add:

```go
// Poll votes arrive encrypted with the poll's own key and name their
// options only as SHA-256 hashes. Decrypt, resolve against the polls
// table, store as media_type="poll_vote" with the poll's id in BOTH
// quoted_message_id and filename (filename is where reactions already
// keep their target — consumers can read either column), then return:
// a vote is not a normal content message. A vote with zero selected
// options is a CLEARED vote — stored with empty content so waiters can
// ignore it, never dropped.
if pollUpdate := msg.Message.GetPollUpdateMessage(); pollUpdate != nil {
    pollID := ""
    if key := pollUpdate.GetPollCreationMessageKey(); key != nil {
        pollID = key.GetID()
    }
    if pollID == "" {
        return
    }
    vote, err := client.DecryptPollVote(context.Background(), msg)
    if err != nil {
        logger.Warnf("Failed to decrypt poll vote for %s: %v", pollID, err)
        return
    }
    var labels []string
    for _, h := range vote.GetSelectedOptions() {
        hexHash := hex.EncodeToString(h)
        var name string
        row := messageStore.db.QueryRow(
            "SELECT option_name FROM polls WHERE message_id = ? AND option_hash = ?",
            pollID, hexHash)
        if scanErr := row.Scan(&name); scanErr != nil {
            logger.Warnf("Poll vote with unknown option hash %s on %s", hexHash, pollID)
            continue
        }
        labels = append(labels, name)
    }
    content := strings.Join(labels, ", ")
    if err := messageStore.StoreMessage(
        msg.Info.ID, chatJID, sender, content,
        msg.Info.Timestamp, msg.Info.IsFromMe,
        "poll_vote", pollID, "", nil, nil, nil, 0, pollID,
    ); err != nil {
        logger.Warnf("Failed to store poll vote: %v", err)
    }
    return
}
```

Note: `StoreMessage` skips rows with empty content AND empty media
type; `"poll_vote"` is non-empty, so cleared votes are stored.

## Rebuild and swap

The bridge source is ONE tree, and both bridge exes are built from it: the
main bridge runs `bridge\whatsapp-bridge\whatsapp-bridge.exe`, the contact
bridge runs `bridge\contact-bridge\whatsapp-bridge.exe`, and the contact
copy is the *same freshly built binary* copied across — it is never built
separately.

Two Windows traps make the obvious procedure fail silently:

- **Windows renames a running `.exe` without complaint.** So `Move-Item`
  succeeding proves nothing about whether the old process died, and the
  swap can appear to work while the old binary keeps serving.
- **`/api/health` is answered just as happily by the old binary.** It is
  useless as a swap check. Probe a route that only the NEW binary has:
  an empty `POST /api/poll` returns **400** from the new binary and
  **404** from the old.

Also never `taskkill /IM whatsapp-bridge.exe` — both bridges share that
image name, so it kills the other channel too. Kill by `ExecutablePath`.

```powershell
$root = "<install>\bridge"
cd "$root\whatsapp-bridge"
go build -o whatsapp-bridge-new.exe .    # must compile clean before anything is stopped

# --- swap one bridge; run this block once per bridge ---
$dir  = "$root\whatsapp-bridge"          # contact bridge: "$root\contact-bridge"
$task = "ShamashBridge"                  # contact bridge: "ShamashContactBridge"
$port = 8080                             # each channel's port comes from config.json

schtasks /End /TN $task
# Kill by ExecutablePath — NOT by image name; the other bridge shares it.
Get-CimInstance Win32_Process -Filter "Name='whatsapp-bridge.exe'" |
    Where-Object { $_.ExecutablePath -eq "$dir\whatsapp-bridge.exe" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Block until the port is actually free — the restart-on-failure task can
# relaunch the old exe, and a live listener means the old one is still up.
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline -and
       (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) {
    Start-Sleep -Milliseconds 500
}

Move-Item "$dir\whatsapp-bridge.exe" "$dir\whatsapp-bridge-old.exe" -Force
# Main bridge: move the new build in. Contact bridge: copy that same exe.
Move-Item "$root\whatsapp-bridge\whatsapp-bridge-new.exe" "$dir\whatsapp-bridge.exe"
#   ...for the contact bridge use instead:
#   Copy-Item "$root\whatsapp-bridge\whatsapp-bridge.exe" "$dir\whatsapp-bridge.exe"

schtasks /Run /TN $task
```

Verify **both** checks on **both** ports before declaring done:

```powershell
$token = (Get-Content "$dir\store\.bridge-token" -Raw).Trim()
$h = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

# 1. connected
Invoke-RestMethod "http://127.0.0.1:$port/api/health" -Headers $h

# 2. NEW binary is the one serving — expect 400 (not 404)
try   { Invoke-RestMethod "http://127.0.0.1:$port/api/poll" -Method Post -Headers $h -Body '{}' }
catch { "status: $($_.Exception.Response.StatusCode)" }   # BadRequest = new, NotFound = old
```

A `404` means the old process is still serving: repeat the kill, confirm
`Get-NetTCPConnection -LocalPort $port` is empty, then re-run the task.

Roll back by stopping the task the same way and moving `-old.exe` back.
