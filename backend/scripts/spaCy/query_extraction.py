import spacy

nlp = spacy.load("en_core_web_sm")

text = "Apple is buying 42 startups quickly in London for $1 billion, because he runs fast!"

doc = nlp(text)

print("POS Tags:")
pos_tags = {}
for token in doc:
    if token.pos_ not in pos_tags:
        pos_tags[token.pos_] = []
    pos_tags[token.pos_].append(token.text)
for pos, words in pos_tags.items():
    print(pos, ":", words)

print("\nDependency Labels (dep_):")
dep_tags = {}
for token in doc:
    if token.dep_ not in dep_tags:
        dep_tags[token.dep_] = []
    dep_tags[token.dep_].append(f"{token.text}<-{token.head.text}")
for dep, examples in dep_tags.items():
    print(dep, ":", examples)

#一句之中決定是statement or question.
doc = nlp(text)
if text.strip().endswith('?') or any(token.text.lower() in ['what', 'how', 'why', 'when', 'where', 'who'] for token in doc):
    print("Question (目的問題)")
else:
    print("Statement")

# 詞義相關例子
for token in doc:
    print(token.text, "lemma:", token.lemma_, "pos:", token.pos_, "dep:", token.dep_, "shape:", token.shape_)

print("Entities:", [(ent.text, ent.label_) for ent in doc.ents])
print("Relations:")
for token in doc:
    if token.dep_ in ["nsubj", "dobj", "pobj"]:
        print(token.head.text, token.dep_, token.text)
# Claim/Summarization simple
print("Summary claim:", " ".join([token.text for token in doc if token.dep_ in ["ROOT", "nsubj", "dobj"]]))