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




def has_delta(string):
    try:
        if '!delta' in string or '&#8710' in string or 'Δ' in string:
            return True
        else:
            return False
    except TypeError:
        print(f'TypeError: {string}')
        return('TypeError')

