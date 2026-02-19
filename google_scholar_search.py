#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@Created on 12/2/23 11:14 AM
@File:google_scholar_search.py
@Author:Zhuoli Yin
@Contact: yin195@purdue.edu
'''
import requests
import pandas as pd
import re
import logging
import time
import os
from tqdm import tqdm
def setup_logging():
    """ Sets up the logging configuration. """
    logging.basicConfig(filename='serpapi_search.log', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
def load_rounded_publication_data(file_path):
    """
    Load the updated dataset with the rounded '10% of publication' values.
    """
    return pd.read_csv(file_path)
def load_queries_from_csv(file_path, topic):
    """
    Loads search queries from a CSV file.

    Args:
        file_path (str): Path to the CSV file containing the search queries.

    Returns:
        list: A list of dictionaries with 'query', 'start_year', and 'end_year'.
    """
    try:
        df = pd.read_csv(file_path)
        df = df[df['topic'] == topic]
        return df.to_dict(orient='records')
    except Exception as e:
        logging.error(f"Error loading queries from CSV: {e}")
        return []
def serpapi_search(query_details, api_key, search_mode, rounded_publication_data, retry_attempts=3, delay=5):
    """
    Performs a SerpAPI search for each query in the list and saves results to files.
    """
    # Define the directory for saving results
    results_dir = 'google_scholar_results'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    for detail in query_details:
        topic, query, start_year, end_year = detail['topic'], detail['query'], detail['start_year'], detail['end_year']
        results_df = pd.DataFrame()

        if search_mode == "year":
            for current_year in tqdm(range(start_year, end_year + 1)):
                max_page = rounded_publication_data.loc[rounded_publication_data['Year'] == current_year, 'Page'].values[0]
                max_pagination = (max_page - 1) * 10  # every page has 10 results.
                pagination = 0
                while pagination <= max_pagination:
                    results_df, new_pagination = search_serpapi_core(api_key, query, pagination, current_year, current_year, results_df, retry_attempts, delay)
                    if results_df is None or new_pagination is None or new_pagination <= pagination:
                        break  # Exit if max retries are reached or no new page
                    pagination = new_pagination

        elif search_mode == "relevance":
            pagination = 0
            max_pagination = max_page * 10
            while pagination <= max_pagination:
                results_df, new_pagination = search_serpapi_core(api_key, query, pagination, start_year, end_year, results_df, retry_attempts, delay)
                if results_df is None or new_pagination is None or new_pagination <= pagination:
                    break  # Exit if max retries are reached or no new page
                pagination = new_pagination

        # Save results to a file in the specified directory
        filename = f"{results_dir}/google_scholar_{re.sub('[^0-9a-zA-Z]+', '_', topic)}_{start_year}_{end_year}_{search_mode}.csv"
        results_df.to_csv(filename, index=False)
        logging.info(f"Saved results for query '{query}' to {filename}")


def search_serpapi_core(api_key, query, pagination, start_year, end_year, results_df, retry_attempts, delay):
    """
    Helper function to perform the SerpAPI search.
    """
    try:
        params = {
            "api_key": api_key,
            "engine": "google_scholar",
            "q": query,
            "hl": "en",
            "start": pagination,
            "as_ylo": start_year,
            "as_yhi": end_year
        }

        response = requests.get("https://serpapi.com/search", params=params)
        response.raise_for_status()
        results = response.json()

        for result in results.get('organic_results', []):
            results_df = results_df.append({
                'Author': result.get('publication_info', {}).get('authors', [{}])[0].get('name'),
                'Title': result.get('title'),
                'Info': result.get('publication_info', {}).get('summary'),
                'Abstract': result.get('snippet'),
                'Year': start_year if start_year == end_year else 'N/A'
            }, ignore_index=True)

        # Pagination handling, turn to next page
        pagination_link = results.get('serpapi_pagination', {}).get('next_link')
        if pagination_link:
            new_pagination = int(re.search('start=\d+', pagination_link).group().split('=')[1])
            return results_df, new_pagination
        else:
            return results_df, None  # No more pages

    except requests.exceptions.RequestException as e:
        logging.error(f"Error during SerpAPI request for query '{query}': {e}")
        retry_attempts -= 1
        if retry_attempts <= 0:
            logging.error(f"Max retries reached for query '{query}'.")
            return None, None  # Exit loop if max retries are reached
        time.sleep(delay)
        return results_df, pagination  # Retry with the same pagination

if __name__ == '__main__':
    """
    Obtain the API key from https://serpapi.com/
    """
    setup_logging()
    api_key = "fef908713d9413f179fe7a8ad547f737155312dfcab73904b139d608ed6b4b9e"

    """
    relevance mode: query the most relevant papers as returned by Google Scholar
    year mode: query top K papers published in each year, such as K = 10 means top 10 papers published in each year 
    """
    search_mode = 'year'  # 'relevant' or 'year
    MAX_PAGE = 1

    file_path = '/Users/zhuoliyin/Library/CloudStorage/OneDrive-purdue.edu/Academic project/15a_NLP-for-LCA/LLM-assisted-LCA/search_query.csv'  # CSV file path
    TOPIC = 'wind turbine system'  # topic to search
    queries = load_queries_from_csv(file_path, topic=TOPIC)

    # Load the updated dataset
    file_path = '/Users/zhuoliyin/Library/CloudStorage/OneDrive-purdue.edu/Academic project/15a_NLP-for-LCA/LLM-assisted-LCA/LCA_publication_per_year_rounded.csv'  # Path to the updated dataset
    rounded_publication_data = load_rounded_publication_data(file_path)

    serpapi_search(queries, api_key, search_mode, rounded_publication_data)

