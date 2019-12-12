To delete a collection you have to:

ssh into the endpoint:
`./bin/bastion.py endpoint ssh --bosslet <bosslet.config>`

Once on the endpoint:
1. `sudo apt-get update`
2. `sudo apt-get install mysql-client`
3. `mysql -h endpoint-db.production.boss -u testuser -p`
4. You will be prompted for a password use the testuser password you can get from running `./bastion.py vault.production.boss vault-read secret/endpoint/django/db`
5. Use boss

Once on the mysql client BOSS database:
1. delete channel from bosscore_source
2. delete channels from experiment
3. delete experiments from collection
4. delete collection from `collection` table
5. delete collection from `lookup` table
6. delete experiments from `lookup` table
7. delete channels from `lookup` table

For reference:
Delete commands: `DELETE FROM bosscore_source WHERE id=<id>`
