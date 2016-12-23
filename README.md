k9db-to-mbox
=====================

Copyright (C) 2016 Richard Gay  
Copyright (C) 2011 Chris McCormick

Released under the MIT license.

## Purpose

At the time of writing, the current version of K-9 Mail (5.010)
does not support exporting e-mails of an POP3 account. K-9 Mail
stores its e-mails locally in an SQLite3 database, in which the
e-mails are decomposed into headers, content, and attachments.
The attachments are stored as separate files.

The goal of this package is to convert a given K-9 Mail SQLite3
database to a series of Mbox files.

## Usage

Here is how one can obtain the K-9 Mail database and convert it
with the help of this script:

1. Make a backup of the phone using the ADB interface:  
```
    adb backup -f k9.ab com.fsck.k9
```

   As usual for ADB, unlock the backup on the phone after
   triggering the above command.

2. Unpack the relevant parts of the backup file  
```
    dd if=k9.ab bs=24 skip=1 | openssl zlib -d | tar -xv "apps/com.fsck.k9/ef"
```

   Running the above command produces a file  
```
    apps/com.fsck.k9/ef/<UID>.db
```

   in your current working directory. This file
   stores the information about the e-mails, excluding
   attachments. The latter are in the directory  
```
    apps/com.fsck.k9/ef/<UID>.db_att
```
    
3. Run this script  
```
    cd apps/com.fsck.k9/ef/
    python2.7 k9db-to-mbox.py <UID>.db
```

## Limitations

The script has been tested with some non-ASCII encodings and
with some content types of attachments. However, there might
still be forms of e-mail that are not properly handled. The
script might warn you when it encounters such case, but please
do not blindly rely on this. Instead, please inspect a
sufficiently large sample set of the e-mails in the resulting
Mbox before deleting the K-9 files.

The script has been tested in combination with the following
third-party tools:

* `python` 2.7.10 (compiled with `sqlite` support),
* Android tools (this includes `adb`) 5.1.1,
* `sqlite` 3.12.0,
* `openssl` 1.0.2h, GNU `tar` 1.28,
* a collection of about 400 e-mails.
