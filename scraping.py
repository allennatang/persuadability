import praw
import time
from convokit import Corpus, Utterance, Speaker, Conversation

import ast
import logging
import pandas as pd
import os
import glob
import re

# Log in

reddit = praw.Reddit(
    client_id = 'CgETnW-X8DU8eCAvgzCJ1g',
    client_secret = 'GFoMEn2R-HdPaxX-7PiCmzPBoiel-Q',
    user_agent= "allenna"
)

# logging 

# # add logging
# handler = logging.StreamHandler()
# handler.setLevel(logging.DEBUG)
# for logger_name in ("praw", "prawcore"):
#     logger = logging.getLogger(logger_name)
#     logger.setLevel(logging.DEBUG)
#     logger.addHandler(handler)

# remove logging if needed 
for logger_name in ("praw", "prawcore"):
    logger = logging.getLogger(logger_name)
    for handler in logger.handlers[:]:  # Copy the list to avoid modification during iteration
        if isinstance(handler, logging.StreamHandler):
            logger.removeHandler(handler)

# smaller subreddit to test out functions on smaller number of posts

subreddit=reddit.subreddit('ChangeMyView').search('flair:"Delta(s) from OP"',limit=3)

def remove_prefix(text, prefix):
    '''removes prefix from string'''
    if text.startswith(prefix):
        return text[len(prefix):]
    return text

def get_utt(speakerCorpus, utteranceCorpus, utt):
    """
    Extracts and processes an utterance from a Reddit submission or comment, updating the speaker and utterance corpora.

    Parameters:
    speakerCorpus (dict): Dictionary mapping speaker IDs to Speaker objects.
    utteranceCorpus (dict): Dictionary mapping utterance IDs to Utterance objects.
    utt (praw.models.Comment or praw.models.Submission): The Reddit comment or submission to process.

    Returns:
    tuple: Updated speakerCorpus and utteranceCorpus dictionaries.
    """
    # handle deleted authors
    if utt.author == None:
        author = '[deleted]'
    else:
        author = utt.author.name
    # add author to speakerCorpus if they are not in yet
    if author not in speakerCorpus:
        speakerCorpus[author] = Speaker(id = author)
    # handles the attributes that are different in comment and submissions
    if isinstance(utt, praw.models.Comment):
        conversation_id = utt.submission.id
        reply_to = remove_prefix(utt.parent_id, 't1_')
        reply_to = remove_prefix(reply_to, 't3_')
        text = utt.body
        utt_meta = {'created_utc': utt.created_utc, 'body_html': utt.body_html, 'edited': utt.edited, 'id': utt.id, 'is_submitter': utt.is_submitter, 'link_id': utt.link_id, 'parent_id': utt.parent_id, 'permalink': utt.permalink, 'replies': utt.replies, 'saved': utt.saved, 'score': utt.score, 'stickied': utt.stickied, 'submission': utt.submission}
    elif isinstance(utt, praw.models.Submission):
        conversation_id = utt.id
        reply_to = None
        text = utt.selftext
        utt_meta = {'created_utc': utt.created_utc, 'edited': utt.edited, 'id': utt.id, 'permalink': utt.permalink, 'distinguished': utt.distinguished, 'is_self': utt.is_self, 'over_18': utt.over_18, 'score': utt.score, 'title': utt.title, 'upvote_ratio': utt.upvote_ratio}
    utteranceCorpus[str(utt.id)] = Utterance(id=utt.id, speaker=speakerCorpus[author], conversation_id=conversation_id, reply_to=reply_to, timestamp = utt.created_utc, text=text, meta=utt_meta)
    return speakerCorpus, utteranceCorpus

def all_comments(speakerCorpus, utteranceCorpus, comments):
    """
    Recursively processes all comments in a Reddit submission, updating the speaker and utterance corpora.

    Parameters:
    speakerCorpus (dict): Dictionary mapping speaker IDs to Speaker objects.
    utteranceCorpus (dict): Dictionary mapping utterance IDs to Utterance objects.
    comments (list): List of Reddit comments to process.

    Returns:
    tuple: Updated speakerCorpus and utteranceCorpus dictionaries.
    """
    for comment in comments:
        if comment == None:
            continue
        if isinstance(comment, praw.models.MoreComments):
            speakerCorpus, utteranceCorpus = all_comments(speakerCorpus, utteranceCorpus, comment.comments())
        else:
            speakerCorpus, utteranceCorpus = get_utt(speakerCorpus, utteranceCorpus, comment)
            if len(comment.replies) != 0:
                speakerCorpus, utteranceCorpus = all_comments(speakerCorpus, utteranceCorpus, comment.replies)
    return speakerCorpus, utteranceCorpus

def comments_up_to(speakerCorpus, utteranceCorpus, comments, n, level=0):
    """
    Recursively processes comments up to a specified depth in a Reddit submission, updating the speaker and utterance corpora.

    Parameters:
    speakerCorpus (dict): Dictionary mapping speaker IDs to Speaker objects.
    utteranceCorpus (dict): Dictionary mapping utterance IDs to Utterance objects.
    comments (list): List of Reddit comments to process.
    n (int): Maximum depth of comments to process.
    level (int): Current depth level (default is 0).

    Returns:
    tuple: Updated speakerCorpus and utteranceCorpus dictionaries.
    """
    for comment in comments:
        if level >= n:
            return speakerCorpus, utteranceCorpus
        if comment == None:
            continue
        if isinstance(comment, praw.models.MoreComments):
            n_level = level + 1
            speakerCorpus, utteranceCorpus = comments_up_to(speakerCorpus, utteranceCorpus, comment.comments(), n, n_level)
        else:
            speakerCorpus, utteranceCorpus = get_utt(speakerCorpus, utteranceCorpus, comment)
            if len(comment.replies) != 0:
                n_level = level + 1
                speakerCorpus, utteranceCorpus = comments_up_to(speakerCorpus, utteranceCorpus, comment.replies, n, n_level)
    return speakerCorpus, utteranceCorpus

def immediate_OP_replies(u_corpus):
    """
    Identifies and extracts all direct replies made by the original poster (OP) in a Reddit conversation.

    Parameters:
    u_corpus (dict): Dictionary mapping utterance IDs to Utterance objects.

    Returns:
    dict: A dictionary containing utterances where the OP is replying to direct responses, including the root utterance.
    """
    OP_corpus = {}
    root_utt = 'placeholder'

    for utt in u_corpus:
        if u_corpus[utt].reply_to == None:
            root_utt = u_corpus[utt]
            OP_corpus[utt] = u_corpus[utt]
        if u_corpus[utt].retrieve_meta('is_submitter') == True:
            OP_corpus[utt] = u_corpus[utt]

    # find all chains where OP is replying to a direct response

    response_corpus = {}

    for utt in OP_corpus:
        target = u_corpus[utt].reply_to
        if target is not None:
            if u_corpus[target].reply_to == u_corpus[target].conversation_id:
                response_corpus[utt] = OP_corpus[utt]
                response_corpus[target] = u_corpus[target]

    response_corpus[root_utt.id] = root_utt
    
    return response_corpus

# '''example usage for submission'''
# submission = reddit.submission(url="https://www.reddit.com/r/changemyview/comments/1g908tr/cmv_all_daytraders_and_retail_traders_are/")
# s_corpus = {}
# u_corpus = {}
# s_corpus, u_corpus = get_utt(s_corpus, u_corpus, submission)
# s_corpus, u_corpus = all_comments(s_corpus, u_corpus, submission.comments)

'''example usage for a single submission'''
submission = reddit.submission(url="https://www.reddit.com/r/changemyview/comments/1g908tr/cmv_all_daytraders_and_retail_traders_are/")
s_corpus = {}
u_corpus = {}
s_corpus, u_corpus = get_utt(s_corpus, u_corpus, submission)
s_corpus, u_corpus = comments_up_to(s_corpus, u_corpus, submission.comments, 2)

s_corpus_all = {}
u_corpus_all = {}
s_corpus_all, u_corpus_all = get_utt(s_corpus, u_corpus, submission)
s_corpus_all, u_corpus_all = all_comments(s_corpus, u_corpus, submission.comments)

scrape_type = 'flair'

if scrape_type == 'controversial':
    subreddit = reddit.subreddit("ChangeMyView").controversial(limit=1000, time_filter="year")
elif scrape_type == 'hot':
    subreddit=reddit.subreddit('ChangeMyView').hot(limit=1000)
elif scrape_type == 'flair':
    subreddit=reddit.subreddit('ChangeMyView').search('flair:"Delta(s) from OP"',limit=100, time_filter="year")
else: 'error: make sure you specify scrape type!!!'


# get the batch number for this scrape based on highest previous number
prev_scrapes = glob.glob(os.path.join('scrape', f"scrape_{scrape_type}_b*.csv"))
if prev_scrapes != []:
    batches = [re.search(r'b(\d+)\.csv$', filename) for filename in prev_scrapes]
    batch_num = max([int(batch.group(1)) for batch in batches]) + 1
else:
    batch_num = 1

df = pd.DataFrame()

full_corpus = {}

post_num = 0

for post in subreddit:
    post_num += 1
    print(post.title)
    print(post.num_comments)
    s_corpus = {}
    u_corpus = {}
    s_corpus, u_corpus = get_utt(s_corpus, u_corpus, post)
    s_corpus, u_corpus = comments_up_to(s_corpus, u_corpus, post.comments, 2)
    for u in u_corpus:
        row={}
        utt = u_corpus[u]
        row['id'] = utt.id
        row['speaker'] = utt.speaker.id
        row['conversation_id'] = utt.conversation_id
        row['reply_to'] = utt.reply_to
        row['timestamp'] = utt.timestamp
        row['text'] = utt.text.replace("\n","\\n")
        row['meta'] = utt.meta
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        # saves posts every so often
        if post_num % 15 == 0:
            df.to_csv(f'scrape/scrape_{scrape_type}_b{batch_num}.csv')

df.to_csv(f'scrape/scrape_{scrape_type}_b{batch_num}.csv')
print("done")

# for u in full_corpus:
#     row={}
#     utt = full_corpus[u]
#     row['id'] = utt.id
#     row['speaker'] = utt.speaker.id
#     row['conversation_id'] = utt.conversation_id
#     row['reply_to'] = utt.reply_to
#     row['timestamp'] = utt.timestamp
#     row['text'] = utt.timestamp
#     row['meta'] = utt.meta
#     df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
#     df.to_csv('testing.csv')



files = [f for f in os.listdir('scrape') if f.endswith('.csv')]

file_dict = {}

for file in files:
    file_dict[file] = pd.read_csv(f"scrape/{file}")

file_dfs = [f for f in file_dict.values()]

final = pd.concat(file_dfs, ignore_index=True)
final = final.drop_duplicates(subset=['id'])

def find_order(conversation_id, reply_to, post_id, speaker_id):
    """
    Determines the order or type of a post within a conversation.

    Parameters:
    conversation_id (int or str): The ID of the conversation.
    reply_to (int or str): The ID of the post to which the current post is replying.
    post_id (int or str): The ID of the current post.
    speaker_id (int or str): The ID of the speaker who made the current post.

    Returns:
    int or str: 
        - 1 if the current post is the original post in the conversation.
        - 2 if the current post is a direct reply to the original post.
        - 3 if the current post is a reply to another post in the conversation and the speaker is the original poster.
        - 'other' if none of the above conditions are met or if an error occurs during the lookup.
    """
    if conversation_id == post_id:
        return 1
    elif reply_to == conversation_id:
        return 2
    else:
        try:
            OP = final[final['id'] == conversation_id]['speaker'].iloc[0]
            responding_to = final[final['id'] == reply_to]['reply_to'].iloc[0]
            if responding_to == conversation_id and speaker_id == OP:
                return 3
            else:
                return 'other'
        except IndexError:
            return 'other'

lambda_order = lambda row: find_order(row['conversation_id'], row['reply_to'], row['id'], row['speaker'])

# def lambda_order(row):
#     # Insert print statements to check row and key operations
#     print(row)  # Uncomment to see each row
#     # Perform calculations or return values as intended
#     return find_order(row['conversation_id'], row['reply_to'], row['id'], row['speaker'])

final['order'] = final.apply(lambda_order, axis=1)

def has_delta(string):
    try:
        if '!delta' in string or '&#8710' in string or 'Δ' in string:
            return True
        else:
            return False
    except TypeError:
        print(f'TypeError: {string}')
        return('TypeError')

def get_reply(reply_to):
    return final[final['id'] == reply_to]['text'].iloc[0]

def get_OP(conversation_id):
    return final[final['id'] == conversation_id]['text'].iloc[0]

def get_OP_title(conversation_id):
    res = ast.literal_eval(final[final['id'] == conversation_id]['meta'].iloc[0])
    return res['title']

final_3 = final[final['order'] == 3].copy()

final_3['text_replyto'] = final_3['reply_to'].apply(lambda x: get_reply(x))
final_3['text_OP'] = final_3['conversation_id'].apply(lambda x: get_OP(x))
final_3['title_OP'] = final_3['conversation_id'].apply(lambda x: get_OP_title(x))

# Apply the has_delta function to the 'text' column
final_3['has_delta'] = final['text'].apply(has_delta)


final_3.to_csv('data/final_order3.csv', index=False)

final_3[final_3['has_delta'] == True]['conversation_id'].nunique()
