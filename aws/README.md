# The weekly digest, on a schedule

StoreSense has no scheduler inside it. A web process quietly emailing on a
timer is a surprising thing to find in a service, and every host already has a
better mechanism — this is one of them.

EventBridge wakes a Lambda on Monday morning, it signs in to the API, and asks
it to send the brief. The function is a single file with no dependencies, so
there's nothing to package and no layer to maintain.

```
EventBridge (cron)  →  Lambda  →  POST /api/login
                                  POST /api/digest/send  →  SMTP → inbox
```

## Deploy it

With the [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/):

```bash
cd aws/digest_scheduler
sam build
sam deploy --guided \
  --parameter-overrides \
    ApiUrl=https://your-api.onrender.com \
    AppPassword=the-same-one-the-api-uses
```

<details>
<summary>Or by hand in the console</summary>

1. **Lambda → Create function**, Python 3.12, paste `handler.py` in.
2. **Configuration → Environment variables**:
   `STORESENSE_API_URL` and `STORESENSE_PASSWORD`.
3. **Configuration → General** → timeout **3 minutes**. The default 3 *seconds*
   is nowhere near enough — signing in to a sleeping API alone can take one.
4. **EventBridge → Schedules → Create**, cron `0 8 ? * MON *`, target this
   function.
</details>

## Test it before trusting the schedule

Invoke it by hand with an empty event `{}`. A working run logs:

```
digest sent to owner@noszn.example
```

Anything else comes back as a `DigestError` naming the URL and the status code,
so CloudWatch tells you whether it was the password, the API being down, or SMTP.

## Things worth knowing

**The first call is slow on purpose.** Free hosting stops the container when
nothing has called it for a while, and weekly is exactly the cadence that
guarantees it's always asleep. The sign-in gets a 60 second timeout so a cold
start reads as a wait rather than an outage.

**The password sits in an environment variable.** For one shop that's a
reasonable place for it. If this were handling anyone else's data it belongs in
Secrets Manager with the function given `secretsmanager:GetSecretValue` — the
change is about ten lines, and the reason to make it is rotation, not secrecy.

**Cost is nil in practice.** Four invocations a month against a free tier of a
million.
