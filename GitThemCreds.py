#/usr/bin/python3
import requests
import time
import sys
import json
import subprocess
import argparse
import yaml
from colorama import init, Fore
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
import csv

#What's a tool without a banner?
with open('.banner', 'r') as f:
	for line in f:
		print(line.rstrip())
print('\n')

parser = argparse.ArgumentParser(description='GitHub API Code Search with Trufflehog')
parser.add_argument('--config', type=str, help='Path to the config file', default='.config.yaml')
parser.add_argument('--domain', type=str, help='Domain name to search on GitHub', required=True)
parser.add_argument('--truffles', action='store_true', help='Run Trufflehog on the search results (./trufflehog git url | tee -a truffle-report.txt)')
parser.add_argument('--pages', type=int, help='Number of pages to query (default: 1)', default=1)
parser.add_argument('--table', action='store_true', help='Display results in a table')

#In progress list:
#parser.add_argument('--or ganization', type=str, nargs='+', help='List of organizations to search GitHub for')
parser.add_argument('--excel', action='store_true', help='Output table contents to an Excel file (in testing)')
parser.add_argument('--status', action='store_true', help='Displays status bar during searching (in testing)')

args = parser.parse_args()

#Initializing all the things
console = Console()
results = []
unique_urls = []
init(autoreset=True)

config_file = args.config
with open(config_file, 'r') as stream:
    try:
        config = yaml.safe_load(stream)
        print('\n[+] Config loaded!\n')
    except yaml.YAMLError as exc:
        print(exc)
github_token = config['github_pat']
queries = config['queries']
with open('output.json', 'w') as f1, open('urls.txt', 'w') as f2:
    pass

#Dirty function to grab dorks from config file
def get_query_parameters(filename):
    with open(filename, 'r') as file:
        data = yaml.safe_load(file)
        queries = data['queries']
        for query in queries:
            yield query

domain = args.domain
filename = args.config
keywords = get_query_parameters(filename)
keywords_generator = get_query_parameters(filename)
keyword_count = sum(1 for _ in keywords_generator)
#Sleep timer, yes this stinks. Every minute. This is because the GitHub API does not like us.
#Adjust at your discretion but during testing this resulted in no errors.
sleep = 65
#Pagination tracker variable
page = 1

#Function for creating and displaying table
def display_table(results):
    table = Table(title=f'Github Recon for {domain}', show_header=True, header_style='bold magenta')
    table.add_column('Repository URL')
    table.add_column('Query')
    table.add_column('Page')
    for repo_url, query, page in results:
        table.add_row(repo_url, query, str(page))
    console.print(table)

#Colors because why not?
print(Fore.GREEN + '========================== Starting GitHub API Code Search ==========================')

#Meat and Potatoes
#I will break this down as best as I can

#This is a for loop over all our dorks loaded from the configuration file
for query in keywords:

    #This allows us to take that keyword and look at different pages from the API call
    for page in range(1, args.pages + 1):
        #Building our URL with the proper headers
        #This may break if version changes, issues authenticating check
        #https://docs.github.com/en/rest/overview/authenticating-to-the-rest-api?apiVersion=2022-11-28
        url = f'https://api.github.com/search/code?q={domain}+{query}&page={page}'
        headers = {
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'Authorization': f'Bearer {github_token}'
        }
        print('\n' + Fore.YELLOW + '[+] Git Search URL: ' + Fore.YELLOW + f'{url}')

        #This is for printing the status bar (in testing)
        if args.status:
            with Progress() as progress:
                task = progress.add_task('[cyan][STATUS]: ', total=keyword_count * args.pages)
                progress.update(task, advance=1)

        #Try and catch all the errors! Print out the API errors to terminal but to not output
        try:
            #Simple GET request here
            response = requests.get(url, headers=headers)
            response_json = response.json()

            #Now the annoying part
            #For loop to put the repository URL but we need to add the .git suffix
            
            if not response_json['items']:
                print(f'\t- No repositories found')
            else:
                for item in response_json['items']:
                    repo_url = item['repository']['html_url']
                    print(f'\t- Repository found: {repo_url}.git')

            #One way to see if we hit rate limiting (this is handled better later on)
            if 'secondary rate limit' in response.text:
                print(f'We hit the rate limit on {query}, pausing here and restarting in 1 min.')
                time.sleep(60)
                response = requests.get(url, headers=headers)
                response_json = response.json()
                sleep += 15

                #Repeating the above code, blasphemy I know, this probably should be a function
                for item in response_json['items']:
                    repo_url = item['repository']['html_url']
                    print(f'\t- Repository found: {repo_url}.git')

            #Dumping output to JSON file
            with open('output.json', 'a', encoding='utf-8') as f:
                json.dump(response_json, f, ensure_ascii=False, indent=4)

            #Dumping URLs to file
            with open('urls.txt', 'a') as f:
                for item in response_json['items']:
                    repo_url = item['repository']['html_url']
                    f.write(f'{repo_url}.git' + '\n')

            #Similar to above but this adds the repository URL to our array
            for item in response_json['items']:
                repo_url = item['repository']['html_url']
                results.append((repo_url, query, page))

            #This is for creating an excel file (in testing)
            if args.excel:
                with open('output.csv', 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([repo_url, query, str(page)])

            #We must do this, or we will hit rate limiting real quick
            time.sleep(sleep) 

            #Adding to our page counter
            if page == args.pages:
                break
            else:
                page +=1 

        #API error handling like a boss, lots of repeat code, create functions I know
        except Exception as e:
            #If we get an API error, it will print to terminal but then repeat the query a minute later
            print(Fore.RED + f'[!] API Error: {response.text}')
            print('\n' + Fore.CYAN + f'[+] Will retry: {url} in 60 seconds')
            time.sleep(60)
            response = requests.get(url, headers=headers)
            response_json = response.json()
            time.sleep(30)
            
            #Same as above
            for item in response_json['items']:
                repo_url = item['repository']['html_url']
                print(f'\t- Repository found: {repo_url}.git')

            with open('output.json', 'a', encoding='utf-8') as f:
                json.dump(response_json, f, ensure_ascii=False, indent=4)

            with open('urls.txt', 'a') as f:
                for item in response_json['items']:
                    repo_url = item['repository']['html_url']
                    f.write(f'{repo_url}.git' + '\n')

            #Don't hate me but we're increasing the sleep timer by 15 seconds, they're onto us!
            sleep += 15

#Creating excel sheet (in testing)
if args.excel:
    print(Fore.YELLOW + 'Generating Excel report...')
    with open(f'gitthemcreds-{domain}.xlsx', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            print(row)

#There's a better way to do this
copy_file = 'sort -u urls.txt > unique_urls.txt'
subprocess.run(copy_file, shell=True, check=True)

#Displaying table to terminal
print('\n')
if args.table:
    display_table(results)

#Running trufflehog on git URLs
if args.truffles:
    print('\n' + Fore.GREEN + '========================== Starting Trufflehog ==========================')
    with open('unique_urls.txt', 'r') as f:
        for url in f:
            url = url.strip()
            command = f'./trufflehog git {url} | tee -a truffle-report.txt'
            #Need this subprocess to do this
            subprocess.run(command, shell=True, check=True)
else:
    print('\n' + Fore.RED + '========================== Skipping Trufflehog ==========================')
