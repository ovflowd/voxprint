# Automations and scripts

A speaker sensor answers "who spoke the last utterance at this satellite", not "who started this
script". These rules keep a script honest:

- **Check that the result is recent.** The sensor keeps its last result until the satellite is used
  again, so compare `last_updated` with `now()`. 30 seconds covers a request and the model's answer.
- **Only trust a voice when nobody is logged in.** A request from the companion app or the browser
  carries `context.user_id`; one from a satellite doesn't. Without this check, someone typing in the
  app within 30 seconds of Alice speaking would pass as Alice.
- **Configure every satellite in your home.** Voxprint can't see a satellite it doesn't listen to, so a
  request there would find another satellite's recent verdict.
- **Don't call gated scripts from automations.** An automation has no user either, and would borrow a
  verdict from the last 30 seconds.
- **Treat anything else as unknown.** A missing sensor, `unknown`, an error or a stale result all mean
  nobody was recognized. The templates below already do.

## Only answer one person

In a script that Assist calls:

```yaml
condition: template
value_template: >-
  {{ not context.user_id
     and states('sensor.kitchen_satellite_speaker') == 'Alice'
     and now() - states.sensor.kitchen_satellite_speaker.last_updated < timedelta(seconds=30) }}
```

It refuses requests from the app, even Alice's own; the next script accepts both.

## A logged-in user or a recognized voice

Assist in the companion app or the browser runs as the logged-in user, so a script sees
`context.user_id`. At a satellite there is no user, and the speaker sensor fills in. This script
returns the user ID of whoever is asking, from either source, or an empty string. Give each speaker a
person when you add them, so their sensor carries the person's `user_id`.

```yaml
alias: Who is asking
mode: parallel
sequence:
  - variables:
      logged_in: "{{ context.user_id if context is defined and context.user_id else '' }}"
      heard: >-
        {%- set heard = expand(integration_entities('voxprint'))
             | selectattr('attributes.threshold', 'defined')
             | selectattr('last_updated', '>', now() - timedelta(seconds=30))
             | sort(attribute='last_updated', reverse=true) | list -%}
        {{ heard[0].attributes.user_id if heard and heard[0].attributes.user_id else '' }}
      result:
        user_id: "{{ logged_in or heard }}"
        by: "{{ 'login' if logged_in else ('voice' if heard else 'unknown') }}"
  - stop: Identified
    response_variable: result
```

It takes the satellite that heard someone most recently, which is the one being talked to unless two
people speak to two satellites within the same 30 seconds; then it may answer with the other one's
speaker. Call it at the start of every script that
reveals or changes something private, and refuse unless `user_id` is someone allowed:

```yaml
- action: script.who_is_asking
  response_variable: asker
- if: "{{ asker.user_id not in ['<user ID of someone allowed>'] }}"
  then:
    - stop: Not allowed
```

Scripts that an LLM conversation agent calls as tools keep the conversation's context, so
`context.user_id` is the app user there too. Don't expose the private entities themselves to Assist:
expose the gated scripts instead, so the check always runs.

## Score sensors for calibration

A template sensor per enrolled speaker plots their score over time, which is what
[calibration](enrollment.md#calibrate) needs:

```yaml
template:
  - sensor:
      - name: Kitchen score Alice
        state: "{{ state_attr('sensor.kitchen_satellite_speaker', 'scores').get('Alice') }}"
```

The same can be made in the UI as a template helper.
