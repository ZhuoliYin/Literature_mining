#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@Created on 5/4/22 10:35 PM
@File:download_XML.py
@Author:Zhuoli Yin
@Contact: yin195@purdue.edu
'''
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

import pickle
import os
import logging
from typing import Dict, Optional
import json
from GPT_engine import run_gpt_conversation_plain_text
from tqdm import tqdm
class AcademicPaperParser:
    def __init__(self, publisher: str, api_key: str, api_url: str, output_dir: str, doi: str):
        self.publisher = publisher
        self.api_key = api_key
        self.api_url = api_url
        self.output_dir = output_dir
        self.doi = doi

    def fetch_paper_data(self, doi: str) -> Optional[str]:
        """
        Fetch the XML data for a given DOI from the publisher's API.

        :param doi: Digital Object Identifier of the paper.
        :return: XML data as string if successful, None otherwise.
        """
        try:
            if self.api_url and (self.publisher == 'Springer' or self.publisher == 'Elsevier'):
                url = self.api_url % (doi, self.api_key)
            elif self.api_url and self.publisher == 'IEEE':
                url = self.api_url % (self.api_key, doi)
            else:
                url = 'https://doi.org/' + doi # use this url if just doing a regular html search without API
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as http_err:
            logging.error(f"HTTP error occurred for DOI {doi}: {http_err}")
        except Exception as err:
            logging.error(f"Error fetching data for DOI {doi}: {err}")
        return None

    def parse_xml(self, xml_data: str) -> Optional[Dict]:
        """
        Parse the XML data into a JSON.

        :param xml_data: XML data as string.
        :return: Parsed data in dictionary format if successful, None otherwise.
        """
        try:
            soup = BeautifulSoup(xml_data, 'html.parser')
            return self._parse_based_on_publisher(soup)
        except Exception as e:
            logging.error(f"Error parsing XML data: {e}")
        return None
    def _parse_based_on_publisher(self, soup: BeautifulSoup) -> Optional[Dict]:
        """
        Delegate the parsing of XML data based on the publisher.

        :param soup: BeautifulSoup object containing the XML data.
        :return: Parsed data in dictionary format if successful, None otherwise.
        """
        if self.publisher == 'Elsevier':
            return self._parse_elsevier(soup)
        elif self.publisher == 'Springer':
            return self._parse_springer(soup)
        elif self.publisher == 'IEEE':
            return self._parse_ieee(soup)
        else:
            # Implement other publishers or a default method
            return None
    def save_data_as_json(self, content: Dict, title: str):
        safe_title = self._sanitize_filename(title)
        file_path = os.path.join(self.output_dir, f"{safe_title}.json")
        with open(file_path, "w") as file:
            json.dump(content, file)

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        disallowed_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in disallowed_chars:
            title = title.replace(char, '')
        return title
    def _parse_ieee(self, soup: BeautifulSoup) -> Dict:
        "can only extract abstract"
        try:
            content = {}

            # Extract the title
            title_elements = soup.find_all('title')
            if title_elements:
                content['Title'] = title_elements[0].text.strip()

            # Extract the abstract
            abstract_elements = soup.find_all(name='abstract')
            if abstract_elements:
                content['Abstract'] = abstract_elements[0].text.strip()

            # Extract the keywords
            keywords_elements = soup.find_all(name='index_terms')
            keywords_elements_1 = keywords_elements[0].find_all(name='term')
            keywords_elements_2 = keywords_elements[0].find_all(name='terms')
            keywords_elements = keywords_elements_1 + keywords_elements_2
            if keywords_elements:
                keywords = [keyword.text.strip() for keyword in keywords_elements]
                keywords_text = '; '.join(keywords)
                content['Keywords'] = keywords_text
            return content
        except Exception as e:
            logging.error(f"Error parsing IEEE XML data: {e}")
            return {}

    def _parse_elsevier(self, soup: BeautifulSoup) -> Dict:
        """
        Parse XML data specific to Elsevier.

        :param soup: BeautifulSoup object containing the XML data.
        :return: Parsed data in dictionary format.
        """
        try:
            content = {}

            # Extract the title
            title_elements = soup.find_all(name='dc:title')
            if title_elements:
                content['Title'] = title_elements[0].text.strip()

            # Extract the abstract
            abstract_elements = soup.find_all(name='abstract')
            if abstract_elements:
                content['Abstract'] = abstract_elements[0].text.replace('\n', ' ')
            else:
                # If 'abstract' tag is not found, look for 'description' tag
                description_elements = soup.find_all(name='dc:description')
                if description_elements:
                    content['Abstract'] = description_elements[0].text.replace('\n', ' ')

            # Extract the keywords, ce:keywords
            keywords_elements = soup.find_all(name='ce:keyword')
            if keywords_elements:
                keywords = [keyword.text.strip() for keyword in keywords_elements]
                keywords_text = '; '.join(keywords)
                content['Keywords'] = keywords_text

            # Extract the main body content
            # content['Sections'] = self._extract_elsevier_sections(soup)
            content.update(self._extract_elsevier_sections(soup))
            return content

        except Exception as e:
            logging.error(f"Error parsing Elsevier XML data: {e}")
            return {}

    def _extract_elsevier_sections(self, soup: BeautifulSoup) -> Dict:
        """
        Extracts the tables and sections from the Elsevier XML data, parsing tables globally.

        :param soup: BeautifulSoup object containing the XML data.
        :return: Sections and tables data in dictionary format.
        """
        content = {}
        section_name = 'ce:section'
        paragraph_name = 'ce:para'
        title_name = 'ce:section-title'
        table_name = 'ce:table'

        # Process tables globally
        for table in soup.find_all(name=table_name):
            table_md = self._parse_elsevier_table(table)
            if table_md:
                table_label = table.find('ce:label').text if table.find('ce:label') else "Unnamed Table"
                content[table_label] = table_md

        # Create a dictionary to hold section content
        sections_content = {}

        for section in soup.find_all(name=section_name):
            try:
                # Extract the section ID
                section_id = section.get('id', '')
                # Check if the section is a top-level section (not a subsection)
                if '.' not in section_id:
                    section_title = section.find(name=title_name).text if section.find(name=title_name) else "Unnamed Section"
                    context = self._extract_section_content(section, paragraph_name, content)
                    sections_content[section_title] = context

            except Exception as e:
                logging.error(f"Error processing section in Elsevier XML: {e}")
                continue

        return sections_content

    def _extract_section_content(self, section, paragraph_name, content):
        """
        Extracts content from a section and its subsections.

        :param section: The current section or subsection.
        :param paragraph_name: The name of the paragraph tag.
        :param content: The content dictionary containing table data.
        :return: Combined text of the section and its subsections.
        """
        context = ''
        for element in section.descendants:
            if element.name == paragraph_name:
                paragraph_text = element.get_text(separator=' ', strip=True)

                # Replace cross-references with appropriate text
                for cross_ref in element.find_all(['ce:cross-ref', 'ce:cross-refs']):
                    cross_ref_text = cross_ref.get_text(strip=True)
                    # Replace with table content if it's a table reference
                    if cross_ref_text in content:
                        paragraph_text = paragraph_text.replace(cross_ref_text, content[cross_ref_text])
                    else:
                        # Remove cross-reference text
                        paragraph_text = paragraph_text.replace(cross_ref_text, '')

                context += paragraph_text + ' '

        return context.strip()

    def _parse_elsevier_table(self, table_wrap: BeautifulSoup) -> str:
        """
        Parses a table element from Elsevier XML data into a Markdown-formatted string.

        :param table_wrap: BeautifulSoup object representing the table element.
        :return: Markdown representation of the table.
        """
        if not table_wrap:
            return ''

        # Extract table label and caption
        table_label = table_wrap.find('ce:label')
        caption_para = table_wrap.find('ce:simple-para')
        caption_text = f"{table_label.text}: {caption_para.text.strip()}" if table_label and caption_para else ''

        try:
            # Start building the Markdown table
            markdown_table = caption_text + '\n\n' if caption_text else ''

            # Extract table headers
            headers = [entry.text.strip() for entry in table_wrap.find_all('thead')[0].find_all('entry')]
            markdown_table += '| ' + ' | '.join(headers) + ' |\n'
            markdown_table += '|-' + '-|-'.join(['' for _ in headers]) + '|\n'

            # Extract and add table rows
            for row in table_wrap.find_all('tbody')[0].find_all('row'):
                row_data = [entry.text.strip() for entry in row.find_all('entry')]
                if row_data:
                    markdown_table += '| ' + ' | '.join(row_data) + ' |\n'
        except:
            # use GPT to parse the table
            # pass
            markdown_table = run_gpt_conversation_plain_text('Just return what is queried without additional clarification: Parse the following table embedded in xml format into a markdown table:\n' + str(table_wrap))
            markdown_table = caption_text + '\n\n' + markdown_table + '\n\n'

        return markdown_table

    def _parse_springer(self, soup: BeautifulSoup) -> Dict:
        """
        Parse XML data specific to Springer.

        :param soup: BeautifulSoup object containing the XML data.
        :return: Parsed data in dictionary format.
        """
        try:
            content = {}

            # Extract the title
            title_element = soup.find('article-title')
            if title_element:
                content['Title'] = title_element.text.strip()

            # Extract the abstract
            abstract_element = soup.find('abstract')
            if abstract_element:
                abstract_text = ' '.join([p.text.strip() for p in abstract_element.find_all('p')])
                content['Abstract'] = abstract_text.replace('\n', ' ')

            # Extract the keywords
            keywords_element = soup.find('kwd-group')
            if keywords_element:
                keywords = [kwd.text.strip() for kwd in keywords_element.find_all('kwd')]
                keywords_text = '; '.join(keywords)
                content['Keywords'] = keywords_text

            # Extract the main body content
            content.update(self._extract_springer_sections(soup)) # directly add the sections to the content dictionary

            return content

        except Exception as e:
            logging.error(f"Error parsing Springer XML data: {e}")
            return {}


    def _extract_springer_sections(self, soup: BeautifulSoup) -> dict:
        """
        Extracts sections from the Springer XML data, including text and embedded tables within paragraphs.
        If a section has sub-sections, only its title is extracted.
        Organizes the data as {"section title": content}.

        :param soup: BeautifulSoup object containing the XML data.
        :return: Dictionary of sections with their titles and content.
        """
        table_content = {}
        # Process tables globally
        for table in soup.find_all('table-wrap'):
            table_md = self._parse_springer_table(table)
            if table_md:
                # table_label = table.find('label').text if table.find('label') else "Unnamed Table"
                table_id = table['id']
                table_content[table_id] = table_md

        sections = {}
        for section in soup.find_all('sec'):
            title = section.find('title').text.strip() if section.find('title') else ''

            # Check if the section has sub-sections
            if section.find('sec', recursive=False) is not None:
                # If it has sub-sections, only use the title
                content = ''
                # skip the next several sub-sections determined by len(   section.find('sec', recursive=False))

            else:
                # Extract content if no sub-sections are present
                content = self._extract_springer_section_content(section, table_content)

            if title or content:
                sections[title] = content

        return sections

    def _extract_springer_section_content(self, section, table_content):
        """
        Extracts and concatenates content from a section, excluding sub-sections.

        :param section: The current section.
        :return: Combined text of the section, excluding any sub-sections.
        """
        content = ''
        # Find and replace any table-wrap elements within the section
        for table in section.find_all('table-wrap'):
            table.replace_with('')

        for paragraph in section.find_all('p', recursive=True):
            # Insert table content if a table reference is found
            for table_ref in paragraph.find_all('xref', attrs={'ref-type': 'table'}):
                table_id = table_ref['rid']
                if table_id in table_content:
                    # paragraph.insert_after(table_content[table_id])
                    table_ref.replace_with(table_content[table_id])

            # Extract text from paragraphs
            text_content = paragraph.get_text(separator=" ", strip=True)
            content += text_content + '\n\n'

        return content

    def _parse_springer_table(self, table_wrap: BeautifulSoup) -> str:
        """
        Parses a table element into a Markdown-formatted string.

        :param table_wrap: BeautifulSoup object representing the table element.
        :return: Markdown representation of the table.
        """
        table = table_wrap.find('table')

        if not table:
            return ''

        # Extract table caption
        table_id = table_wrap.find('label')
        caption = table_wrap.find('caption')
        caption_text = f"{table_id.text}: {caption.text.strip()}" if caption and table_id else ''

        try:
            # Extract table headers
            headers = [th.text.strip() for th in table.find_all('th')]

            # Start building the Markdown table
            markdown_table = caption_text + '\n\n' if caption_text else ''
            markdown_table += '| ' + ' | '.join(headers) + ' |\n'
            markdown_table += '|-' + '-|-'.join(['' for _ in headers]) + '|\n'

            # Extract and add table rows
            for tr in table.find_all('tr'):
                row = [td.text.strip() for td in tr.find_all('td')]
                if row:
                    markdown_table += '| ' + ' | '.join(row) + ' |\n'

        except:
            # use GPT to parse the table
            pass
            # markdown_table = run_gpt_conversation_plain_text('Just return what is queried without additional clarification: Parse the following table embedded in xml format into a markdown table:\n' + str(table_wrap))
            # markdown_table = caption_text + '\n\n' + markdown_table + '\n\n'
        return markdown_table
    def parse_general_html(self, soup: BeautifulSoup) -> Dict:
        # Implementation of general html parsing
        pass


if __name__ == '__main__':
    PUBLISHER = 'IEEE'  # '' Springer
    API_KEY = {'Elsevier': 'fedd08d2802b3b824299df99a9f9e0c4', 'Springer': 'ba80a483c4395a76e464022949db9d5a', 'IEEE': 'drhe2kgc5mqszmqm5c6hurhe'}

    # API URL will be filled with API Key and DOI, respectively
    API_URL = {'Elsevier': 'https://api.elsevier.com/content/article/doi/%s?APIKey=%s',
               'Springer': 'https://spdi.public.springernature.app/xmldata/jats?q=doi:%s&api_key=%s/purdue-uni-api',
               'IEEE': 'https://ieeexploreapi.ieee.org/api/v1/search/articles?apikey=%s&format=xml&max_records=25&start_record=1&sort_order=asc&sort_field=article_number&doi=%s'}


    paper_info_df = pd.read_csv(
        '/Volumes/negishi-scratch/NLP_for_LCA/Auto-LCA/eligibility_crossref_wind_turbine_system_1993_2022_year_elsevier_springer_IEEE_abstract_added.csv')
    paper_info_df = paper_info_df.fillna(0)

    # only keep the papers published by the specified publisher
    paper_info_df = paper_info_df[paper_info_df['publisher'].str.contains(PUBLISHER)]

    for _, row in tqdm(paper_info_df.iterrows(), total=paper_info_df.shape[0]):
        doi = row['DOI']
        title = row['title']
        eligibility = row['relevance']

        #### enable this if focusing on the eligible papers
        if eligibility == 'yes':
            continue

        ### enable this if focusing on the papers without abstract yet
        # if row['Abstract'] != '-1':
        #     continue


        ## API key should not be used more than 10 times per second
        if PUBLISHER == 'IEEE':
            time.sleep(0.1)

        parser = AcademicPaperParser(PUBLISHER, API_KEY[PUBLISHER], API_URL[PUBLISHER], f'/Users/zhuoliyin/Library/CloudStorage/OneDrive-purdue.edu/Academic project/15a_NLP-for-LCA/LLM-assisted-LCA/collect_and_parse_papers/json_results/{PUBLISHER}', doi)
        xml_data = parser.fetch_paper_data(doi)
        if xml_data:
            try:
                content = parser.parse_xml(xml_data)
                parser.save_data_as_json(content, title)
            except Exception as e:
                print(f"Error parsing XML data: {e}")
                logging.error(f"Error parsing XML data: {e}")
        else:
            print(f"Could not fetch data for DOI {doi}")