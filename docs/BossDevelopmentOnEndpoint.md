# Boss Development on the Endpoint

## Setup

These directions show how to work directly on the endpoint for Boss development.

Make sure you disable health checks so the endpoint the autoscale group (ASG)
doesn't terminate your endpoint while you're using it.  Any work you have on
it will be lost unless you pushed it back to GitHub.

```shell
# Make sure health checks and termination disabled for the endpoint!
# From boss-manage/bin
python suspend_termination.py endpoint.shared.boss
```

Initial setup steps after logging onto the endpoint.  These steps assume you
want to put the Boss repo in `~/boss`:

```shell
# Make sure health checks and termination disabled for the endpoint!
# Clone the repo to the endpoint (fill in your GitHub username in the URL)
git clone https://<your_github_username>@github.com/jhuapl-boss/boss

cd boss/django

# Make sure your Git identity is set.  I keep a copy of my dotfiles on GitHub,
# but here's how to do it manually. Use your acutal name and email so changes 
# can be tracked to the correct person.
git config user.name "Boss Dev"
git config user.email bossdev@jhuapl.edu

# Create your branch
git checkout integration -b my-branch

# Because we're using https from the load balancer, I don't think we can use
# the Django development server.  Therefore, we'll create a symbolic link that
# points at the boss repo.
sudo mv /srv/www /srv/www-orig
sudo ln -s ~/boss /srv/www

# Perform any necessary database migrations
python3 manage.py makemigrations

# sudo required for this command because it writes to /var/www/static
sudo python3 manage.py collectstatic

# Reload the Django app.  uwsgi-emperor is a WSGI server that hosts the Django app
# Use this command anytime you want to load new changes.
sudo service uwsgi-emperor reload
```

After this initial setup, you just need to use the `reload` command to look at
your changes.

```shell
sudo service uwsgi-emperor reload
```

Follow the normal Git workflow for pushing your changes back to GitHub.

## Cleanup

To restore health checks, run this command from your local `boss-manage/bin`:

```shell
python suspend_termination.py --reverse endpoint.shared.boss
```
