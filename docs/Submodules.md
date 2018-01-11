Git Submodules
==============

All content is derived from [Pro Git](https://git-scm.com/book/en/v2/Git-Tools-Submodules)

**NOTE:** these steps expect development to be done in a seperate copy of the
submodule repositories. It is possible to do development within the submodule
but it takes a couple of extra steps (described in the Pro Git book linked
above)

## Cloning the boss-manage repository
If you are cloning a new copy of the repository:
`git clone --recursive https://github.com/jhuapl-boss/boss-manage.git`

If you are updating an existing repository for the first time after submodules
have been added:
```
git pull
git submodule init
git submodule update
```

**NOTE:*** If you have the repositories currently cloned at the required
locations, delete them first or git-submodules will have problems.

## Updating referenced repository versions
`git submodule update --remote`

## To change the referenced branch (local)
If you are making changes in a branch that is different from integration and
want to test those changes (without pointing everyone at your branch) you can
override what is in .gitmodules
`git config submodule.salt_stack/salt/boss/files/boss.git.branch <branch name>`

To remove this local configuration change, edit .git/config and remove the `branch=`
line.

## To change the referenced branch (everyone)
Edit .gitmodules and change the branch name for the submodule. This should only
be needed when creating or merging branches (merging integration into master).