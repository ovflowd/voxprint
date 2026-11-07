# Changelog

## 0.1.1

- One embedding at a time with a plain bounded queue: requests beyond five get `503` until the queue drains.
- Speech frames are found without an index matrix; the embeddings are unchanged.

## 0.1.0

- First release: WeSpeaker ResNet34-LM speaker embeddings, one utterance at a time, nothing stored.
