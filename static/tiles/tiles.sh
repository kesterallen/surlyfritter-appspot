
full_width=8192 # 256*2^5, note 5

for i in $(seq 0 5); do
    numbins_minus_one=$(echo "2^$i-1" | bc)
    for j in $(seq 0 $numbins_minus_one); do
        mkdir -p $i/$j
    done
    cropsize=$(echo "$full_width/ 2^$i" | bc)

    convert venus_full_square.jpg -crop ${cropsize}x${cropsize} -resize 256x256 -set filename:tile "$i/%[fx:page.x/256]/%[fx:page.y/256]" "%[filename:tile].jpg"
done
