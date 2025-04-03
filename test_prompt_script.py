import pandas as pd

sample = pd.read_csv('data/final_200sample_03102025.csv')

from openai import OpenAI
client = OpenAI()

def result(model, system_prompt, user_prompt, temp=0.55):
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        temperature=temp
    )
    return completion.choices[0].message.content



template_system = """You are simulating a response from an Original Poster (OP) in a Reddit discussion on the /r/ChangeMyView subreddit. You will be provided with the title and body of the OP's post expressing their initial view on the topic. Additionally, you will receive a top-level comment responding to the OP's post.

As the OP, your task is to respond thoughtfully to the comment, considering whether the arguments presented have changed your view. You must decide whether to award a 'delta' (Δ) based on the following criteria:

### When to Award a Delta:
- Your view has significantly changed, even if not completely reversed.
- A key aspect of your argument has been revised after considering the response.
- The response provides an insight that alters how you evaluate the topic, even if you maintain some of your original stance.
- You now recognize an exception or nuance you hadn't considered before.

### When Not to Award a Delta:
- You already agreed with the argument before it was presented.
- The comment makes a good point, but it does not change how you think about the issue.
- You find the argument thought-provoking but not strong enough to alter your stance.

### Borderline Cases (Use Judgment):
- If you acknowledge the argument as valid and important, but your stance remains largely the same, consider awarding a delta if it influences how you present or justify your position.
- If you previously ignored an important factor and now see its relevance, a delta may be appropriate even if you do not fully change your mind.

### Instructions:
1. Read the title and body of the OP’s initial post.
2. Read the top-level comment responding to your post.
3. Write a response emulating the OP’s voice, engaging with the argument thoughtfully.
4. Decide whether to award a delta (Δ) based on the criteria:
5. If awarding a delta, include '!delta' or 'Δ' in your response.
6. If not awarding a delta, ensure these symbols are not present.
7. Keep your response concise and direct while still addressing key arguments.
8. Aim for 3-5 sentences, unless a more detailed explanation is necessary.
---
**Title of OP's Initial Post:**  
{title_OP}

**Body of OP's Initial Post:**  
{text_OP}
"""






template_user = """Here is a top-level comment responding to your post and challenging your view.

**Top-Level Comment Responding to OP's Post:**  
{text_replyto}

**OP’s Response:**  
- Start your response here. Address the comment’s points, reflect on whether they have changed your view, and conclude with your decision on awarding a delta.  
- If awarding a delta, make sure to include **'!delta' or 'Δ'** in your response.
"""

model = 'gpt-4o'

results = pd.DataFrame({'id':[],
    'speaker':[],
    'conversation_id':[],
    'reply_to':[],
    'timestamp':[],
    'text':[],
    'meta':[],
    'order':[],
    'text_replyto':[],
    'text_OP':[],
    'title_OP':[],
    'has_delta':[],
    'response_LLM':[]})


real_user_posts = open("data/results_filtered.json", "r").read()
print(real_user_posts)
for index, row in sample.iterrows():
    title_OP = row['title_OP']
    text_OP = row['text_OP']
    text_replyto = row['text_replyto']
    

    system_prompt = template_system.format(title_OP=title_OP, text_OP=text_OP, real_user_posts=real_user_posts)
    user_prompt = template_user.format(text_replyto=text_replyto)

    response_LLM = result(model, system_prompt, user_prompt)
    print(response_LLM)

    sample.at[index, 'Response_LLM'] = response_LLM

    sample.to_csv(f'data/results_{model}.csv', index=False)

res_path = "data/results_gpt-4o.csv"

res_df = pd.read_csv(res_path)

# create column for LLM delta

def has_delta(text):
    if '!delta' in text or 'Δ' in text:
        return True
    else:
        return False

res_df['LLM_delta'] = res_df['Response_LLM'].apply(lambda x: has_delta(x))

# evaluate correctness

def score(row):
    try:
        if row['LLM_delta'] == True and row['has_delta'] == True:
            return 'TP'
        if row['LLM_delta'] == False and row['has_delta'] == True:
            return 'FN'
        if row['LLM_delta'] == True and row['has_delta'] == False:
            return 'FP'
        if row['LLM_delta'] == False and row['has_delta'] == False:
            return 'TN'
    except KeyError:
        print(row)
    
res_df['result'] = res_df.apply(lambda x: score(x), axis=1)

import json

def format_for_gpt(res_df):
    data = []
    for _, row in res_df.iterrows():
        data.append({
            "title_OP": row["title_OP"],
            "text_OP": row["text_OP"],
            "text_replyto": row["text_replyto"],
            "LLM_response": {
                "text": row["Response_LLM"],  # If you store the LLM's actual reply
                "gave_delta": bool(row["LLM_delta"])
            },
            "actual_user": {
                "text": row["text"],
                "gave_delta": bool(row["has_delta"])
            }
        })
    return json.dumps(data, indent=4)

# Save to a file
with open("persuasion_data.json", "w") as f:
    f.write(format_for_gpt(res_df))

import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score

# Example DataFrame
data = {'result': ['TP', 'TN', 'FP', 'FN', 'TP', 'FP', 'TN', 'FN', 'TP', 'TN']}
df = res_df

# Count occurrences of each result type
confusion_counts = df['result'].value_counts()

# Extract TP, TN, FP, FN counts
TP = confusion_counts.get('TP', 0)
TN = confusion_counts.get('TN', 0)
FP = confusion_counts.get('FP', 0)
FN = confusion_counts.get('FN', 0)

# Calculate the metrics
accuracy = (TP + TN) / (TP + TN + FP + FN)
precision = TP / (TP + FP) if TP + FP > 0 else 0
recall = TP / (TP + FN) if TP + FN > 0 else 0
f1 = 2 * (precision * recall) / (precision + recall) if precision + recall > 0 else 0

print(f'Accuracy: {accuracy}')
print(f'Precision: {precision}')
print(f'Recall: {recall}')
print(f'F1: {f1}')

import os
# Define the CSV file to store results
csv_filename = "prompt_evaluation.csv"

# Create a DataFrame for the new entry
new_entry = pd.DataFrame([{
    "System Prompt": template_system,
    "User Prompt": template_user,
    "Accuracy": accuracy,
    "Precision": precision,
    "Recall": recall,
    "F1": f1
}])

# Append to CSV (create file if it doesn't exist)
if os.path.exists(csv_filename):
    new_entry.to_csv(csv_filename, mode='a', header=False, index=False)
else:
    new_entry.to_csv(csv_filename, mode='w', header=True, index=False)

print(f"New prompt and evaluation metrics saved to {csv_filename}")