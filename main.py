import praw
import time
from convokit import Corpus, Utterance, Speaker, Conversation

import ast
import logging
import pandas as pd
import os
import glob
import re
import time

from functions import remove_prefix, get_utt, all_comments, comments_up_to, immediate_OP_replies, has_delta
# Log in

def scrape_posts(subreddit, scrape_type):
    
    # remove logging if needed 
    for logger_name in ("praw", "prawcore"):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:  # Copy the list to avoid modification during iteration
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)

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
                df.to_csv(f'scrape/scrape_{scrape_type}_b{batch_num}.csv', encoding='utf-8')

            # if post_num % 100 == 0:
            #     time.sleep(300)  # Wait 5 minutes before continuing (adjust as needed)

    df.to_csv(f'scrape/scrape_{scrape_type}_b{batch_num}.csv', encoding='utf-8')
    print("done the scrape batch")

    files = [f for f in os.listdir('scrape') if f.endswith('.csv')]

    file_dict = {}

    for file in files:
        file_dict[file] = pd.read_csv(f"scrape/{file}", encoding='utf-8')

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

    final['order'] = final.apply(lambda_order, axis=1)


    final_3 = final[final['order'] == 3].copy()

    def get_reply(reply_to):
        return final[final['id'] == reply_to]['text'].iloc[0]

    def get_OP(conversation_id):
        return final[final['id'] == conversation_id]['text'].iloc[0]

    def get_OP_title(conversation_id):
        res = ast.literal_eval(final[final['id'] == conversation_id]['meta'].iloc[0])
        return res['title']

    final_3['text_replyto'] = final_3['reply_to'].apply(lambda x: get_reply(x))
    final_3['text_OP'] = final_3['conversation_id'].apply(lambda x: get_OP(x))
    final_3['title_OP'] = final_3['conversation_id'].apply(lambda x: get_OP_title(x))

    # Apply the has_delta function to the 'text' column
    final_3['has_delta'] = final['text'].apply(has_delta)


    final_3.to_csv('data/final_order3.csv', encoding='utf-8', index=False)

    final_3[final_3['has_delta'] == True]['conversation_id'].nunique()

def main():
    
    reddit = praw.Reddit(
        client_id = 'CgETnW-X8DU8eCAvgzCJ1g',
        client_secret = 'GFoMEn2R-HdPaxX-7PiCmzPBoiel-Q',
        user_agent= "allenna",
        config={"retry_on_rate_limit": True}  # Automatically retry after hitting rate limits
    )

    while True:
        scrape_types = ['flair','controversial','hot']

        for scrape_type in scrape_types:
            if scrape_type == 'controversial':
                subreddit = reddit.subreddit("ChangeMyView").controversial(limit=1000, time_filter="year")
            elif scrape_type == 'hot':
                subreddit=reddit.subreddit('ChangeMyView').hot(limit=1000)
            elif scrape_type == 'flair':
                subreddit=reddit.subreddit('ChangeMyView').search('flair:"Delta(s) from OP"',limit=1000, time_filter="year")
            else: 'error: make sure you specify scrape type!!!'

            # Run your scraping function here
            scrape_posts(subreddit, scrape_type)
            
            print("Batch complete.")
            # time.sleep(600)  # Wait 10 minutes before restarting (adjust as needed)

if __name__ == "__main__":
    main()